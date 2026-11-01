"""Fyll demoinstansen (demo.expensevibe.se) med demodata, som scripts/seed_demo.py i SaldoVibe.

Fyra påhittade användare - en administratör, en attestant och två anställda - med utlägg
(inskickade, attesterade, avvisade, exporterade), kilometerrapporter, frånvaro och tidrapporter
över de senaste månaderna, okopplade kvitton i inkorgen och en körd Visma-export. Allt skrivs via
samma formulär och modellmetoder som webben och appen använder.

Befintliga konton och data rörs inte: kategorier, km-sats, frånvaroarter och perioder skapas
bara om de saknas, och skriptet vägrar köra om demoanvändarna redan finns. Datumen räknas bakåt
från i dag, så demon är aktuell när skriptet körs.

Körs med manage.py shell, i webbcontainern som appuser (docker exec går förbi entrypointen och
landar som root, då blir bilagefilerna root-ägda). Alla fyra konton får samma lösenord,
DEMO_PASSWORD; utan det slumpas ett som skrivs ut:

    docker compose exec -T -e DEMO_PASSWORD='...' \
        web gosu appuser /opt/venv/bin/python /app/manage.py shell < scripts/seed_demo.py

Lokalt mot en engångsdatabas:

    EXPENSEVIBE_DATA_DIR=/tmp/demo .venv/bin/python manage.py migrate
    EXPENSEVIBE_DATA_DIR=/tmp/demo .venv/bin/python manage.py shell < scripts/seed_demo.py
"""

import os
import secrets
import sys
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction as db_transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from absence.forms import AbsenceEntryForm
from absence.models import AbsenceSettings, AbsenceType, Period, TimeReport
from absence.services import submit_time_report
from absence.views import save_entry
from attachments.models import Attachment
from attachments.services import save_attachment_with_thumbnail
from expenses.forms import ExpenseForm
from expenses.models import Category, Expense
from export.models import ExportBatch
from export.services import build_tlu_export
from mileage.forms import MileageReportForm
from mileage.models import MileageRate, MileageReport

TODAY = timezone.localdate()
DOMAIN = "demo.expensevibe.se"

# (e-post, förnamn, efternamn, anställningsnummer, roll)
USERS = [
    ("admin", "Johan", "Ek", "9001", "admin"),
    ("attestant", "Karin", "Holm", "9002", "approver"),
    ("erik", "Erik", "Lund", "9003", "employee"),
    ("sara", "Sara", "Nyberg", "9004", "employee"),
]

# Kategorier: (namn, löneart i Visma). Frånvaroarter: (namn, tidkod, granularitet).
CATEGORIES = [
    ("Resa", "710"),
    ("Hotell", "711"),
    ("Representation", "712"),
    ("Förbrukningsmaterial", "713"),
    ("Parkering", "714"),
    ("Övrigt", "719"),
]
ABSENCE_TYPES = [
    ("Sjuk", "801", AbsenceType.Granularity.HOURS),
    ("Vård av barn", "802", AbsenceType.Granularity.HOURS),
    ("Semester", "803", AbsenceType.Granularity.WHOLE_DAY),
    ("Tjänstledig", "804", AbsenceType.Granularity.WHOLE_DAY),
]

# Utlägg: (beskrivning, kategori, belopp inkl. moms, momssats %, dagar sedan, status)
# Kilometerrapporter: (från, till, syfte, km, dagar sedan, status)
# Frånvaro: (månader sedan, index bland månadens arbetsdagar, frånvaroart, timmar eller None)
# Inkorg (okopplade kvitton): (butik, belopp, dagar sedan)
# Status: submitted | approved | rejected | exported. Avvisade får kommentaren i REJECTIONS.
EMPLOYEES = {
    "erik": {
        "expenses": [
            ("Tåg Stockholm–Göteborg t/r", "Resa", "1 348.00", 6, 70, "exported"),
            ("Hotell Göteborg, kundmöte", "Hotell", "1 695.00", 12, 69, "exported"),
            ("Lunch med kund, Nordic Partners", "Representation", "624.00", 12, 40, "approved"),
            ("Parkering Arlanda", "Parkering", "320.00", 25, 18, "approved"),
            ("Skärmkabel till kontoret", "Förbrukningsmaterial", "249.00", 25, 9, "rejected"),
            ("Taxi till kundmöte", "Resa", "412.00", 6, 3, "submitted"),
        ],
        "trips": [
            ("Stockholm", "Uppsala", "Kundmöte Lindqvist Bygg", "142", 55, "exported"),
            ("Stockholm", "Västerås", "Installation hos kund", "220", 22, "approved"),
            ("Stockholm", "Södertälje", "Platsbesök", "76", 2, "submitted"),
        ],
        "absence": [
            (2, 3, "Sjuk", "8"),
            (2, 4, "Sjuk", "8"),
            (1, 7, "Semester", None),
            (1, 8, "Semester", None),
            (0, 1, "Vård av barn", "4"),
        ],
        "inbox": [("Pressbyrån Centralen", "89.00", 1)],
    },
    "sara": {
        "expenses": [
            ("Flyg Stockholm–Malmö t/r", "Resa", "2 180.00", 6, 65, "exported"),
            ("Mässavgift Elmia", "Övrigt", "1 500.00", 25, 48, "approved"),
            ("Fika med leverantör", "Representation", "186.00", 12, 30, "approved"),
            ("Kontorsmaterial", "Förbrukningsmaterial", "478.00", 25, 12, "submitted"),
            ("Parkering Malmö C", "Parkering", "140.00", 25, 5, "submitted"),
        ],
        "trips": [
            ("Malmö", "Lund", "Kundmöte Skånemejerier", "38", 60, "exported"),
            ("Malmö", "Helsingborg", "Leverantörsbesök", "128", 15, "rejected"),
            ("Malmö", "Ystad", "Mässa", "124", 4, "submitted"),
        ],
        "absence": [
            (2, 10, "Semester", None),
            (1, 2, "Sjuk", "4"),
            (1, 12, "Tjänstledig", None),
        ],
        "inbox": [("Clas Ohlson", "329.00", 2), ("Circle K", "612.00", 1)],
    },
}
REJECTIONS = {
    Expense: "Kabeln är kontorsmaterial som beställs via inköp, inte utlägg.",
    MileageReport: "Fel datum - resan gjordes enligt kalendern veckan innan.",
}


def money(value):
    return Decimal(value.replace(" ", "")).quantize(Decimal("0.01"))


def ago(days):
    return TODAY - timedelta(days=days)


def month_start(months_ago):
    year, month = divmod(TODAY.year * 12 + TODAY.month - 1 - months_ago, 12)
    return TODAY.replace(year=year, month=month + 1, day=1)


def workdays(month):
    """Månadens rapporterbara dagar fram till i dag (inga helger, se AbsenceSettings)."""
    blocks = AbsenceSettings.get_solo().blocks_date
    day = month
    while day.month == month.month and day <= TODAY:
        if not blocks(day):
            yield day
        day += timedelta(days=1)


def receipt_png(title, day, total, vat_rate):
    """En PNG som ser tillräckligt mycket ut som ett kvitto för bilagelistan och förhandsvisningen.
    Pillows medföljande typsnitt saknar å/ä/ö, så texten på bilden transkriberas."""
    vat = (total * vat_rate / (100 + vat_rate)).quantize(Decimal("0.01"))
    lines = [day.isoformat(), f"Moms {vat_rate} %: {vat} kr", f"Totalt {total} kr"]
    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    ascii_only = str.maketrans("åäöÅÄÖ–", "aaoAAO-")
    draw.text((40, 40), title.translate(ascii_only), fill="black", font=ImageFont.load_default(size=40))
    for i, line in enumerate(lines):
        draw.text((40, 120 + 46 * i), line.translate(ascii_only), fill="black", font=ImageFont.load_default(size=30))
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def attachment(user, title, day, total, vat_rate=25):
    png = ContentFile(receipt_png(title, day, total, vat_rate), name=f"kvitto-{day}.png")
    att = Attachment(uploaded_by=user, file=png)
    save_attachment_with_thumbnail(att)
    return att


def valid_form(form):
    if not form.is_valid():
        raise SystemExit(f"{type(form).__name__}: {form.errors.as_json()}")
    return form


def decide(item, status, approver):
    if status in ("approved", "exported"):
        item.approve(approver)
    elif status == "rejected":
        item.reject(approver, REJECTIONS[type(item)])
    return item if status == "exported" else None


def seed_settings(admin):
    for name, code in CATEGORIES:
        Category.objects.get_or_create(name=name, defaults={"code": code})
    for name, code, granularity in ABSENCE_TYPES:
        AbsenceType.objects.get_or_create(name=name, defaults={"export_code": code, "granularity": granularity})
    last_new_year = TODAY.replace(year=TODAY.year - 1, month=1, day=1)
    if MileageRate.current(on_date=last_new_year) is None:
        # Skatteverkets schablon 25 kr/mil.
        MileageRate.objects.create(
            amount_per_km=Decimal("2.50"), export_code="730", valid_from=last_new_year, created_by=admin
        )
    for months_ago in range(3):
        Period.objects.get_or_create(month=month_start(months_ago))


def seed_employee(user, spec, approver):
    categories = {category.name: category.pk for category in Category.objects.all()}
    types = {absence_type.name: absence_type.pk for absence_type in AbsenceType.objects.all()}
    exported = []

    for description, category, total, vat_rate, days, status in spec["expenses"]:
        total = money(total)
        form = valid_form(
            ExpenseForm(
                {
                    "category": categories[category],
                    "description": description,
                    "expense_date": ago(days).isoformat(),
                    "amount": total,
                    "vat_amount": (total * vat_rate / (100 + vat_rate)).quantize(Decimal("0.01")),
                    "currency": "SEK",
                }
            )
        )
        expense = form.save(commit=False)
        expense.employee = user
        expense.attachment = attachment(user, description, ago(days), total, vat_rate)
        expense.save()
        exported.append(decide(expense, status, approver))

    for start, end, purpose, km, days, status in spec["trips"]:
        form = valid_form(
            MileageReportForm(
                {
                    "date": ago(days).isoformat(),
                    "start_location": start,
                    "end_location": end,
                    "purpose": purpose,
                    "distance_km": km,
                }
            )
        )
        report = form.save(commit=False)
        report.employee = user
        report.recalculate_compensation()
        report.save()
        exported.append(decide(report, status, approver))

    days_by_month = {months_ago: list(workdays(month_start(months_ago))) for months_ago in range(3)}
    for months_ago, index, type_name, hours in spec["absence"]:
        days = days_by_month[months_ago]
        if index >= len(days):
            continue  # tidigt i månaden - dagen har inte kommit än
        form = valid_form(
            AbsenceEntryForm({"date": days[index].isoformat(), "absence_type": types[type_name], "hours": hours})
        )
        if save_entry(form, employee=user) is None:
            raise SystemExit(f"AbsenceEntryForm: {form.errors.as_json()}")

    # Två månader sedan: attesterad och exporterad. Förra månaden: inskickad (Erik) resp.
    # attesterad (Sara) så attestkön och exportsidan har något att visa. Innevarande: inte färdig.
    for months_ago, status in ((2, "exported"), (1, "approved" if user.email.startswith("sara") else "submitted")):
        submit_time_report(user, month_start(months_ago))
        report = TimeReport.objects.get(employee=user, period__month=month_start(months_ago))
        exported.append(decide(report, status, approver))

    for shop, total, days in spec["inbox"]:
        attachment(user, shop, ago(days), money(total))

    return [item for item in exported if item is not None]


def export(items, admin):
    """Som export:export_create - en batch med .tlu-fil, raderna märks exporterade."""
    expenses = [i for i in items if isinstance(i, Expense)]
    mileage = [i for i in items if isinstance(i, MileageReport)]
    time_reports = [i for i in items if isinstance(i, TimeReport)]
    period_from, period_to = month_start(2), month_start(1) - timedelta(days=1)
    batch = ExportBatch.objects.create(
        created_by=admin,
        period_from=period_from,
        period_to=period_to,
        expense_count=len(expenses),
        mileage_count=len(mileage),
        time_report_count=len(time_reports),
        total_amount=sum(e.amount for e in expenses) + sum(m.compensation_amount for m in mileage),
    )
    file_bytes = build_tlu_export(expenses, mileage, time_reports, period_from, period_to)
    batch.file.save(f"utlagg_{batch.pk}.tlu", ContentFile(file_bytes), save=True)
    for item in items:
        item.mark_exported(batch)
    Period.objects.filter(month=period_from).update(status=Period.PeriodStatus.REPORTED, reported_at=timezone.now())


def main():
    emails = {key: f"{key}@{DOMAIN}" for key, *_ in USERS}
    User = get_user_model()
    if User.objects.filter(email__in=emails.values()).exists():
        sys.exit("Demoanvändarna finns redan - inget gjort.")
    password = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)

    with db_transaction.atomic():
        users = {}
        for key, first_name, last_name, employment_number, role in USERS:
            users[key] = User.objects.create_user(
                email=emails[key],
                password=password,
                first_name=first_name,
                last_name=last_name,
                employment_number=employment_number,
                is_admin=role == "admin",
                is_approver=role == "approver",
                must_change_password=False,
            )
        seed_settings(users["admin"])
        exported = []
        for key, spec in EMPLOYEES.items():
            exported += seed_employee(users[key], spec, users["attestant"])
        export(exported, users["admin"])

    print("Demoanvändare (samma lösenord):")
    for key, first_name, last_name, _, role in USERS:
        print(f"  {emails[key]:32} {first_name} {last_name} ({role})")
    if "DEMO_PASSWORD" not in os.environ:
        print(f"Lösenord: {password}")


main()
