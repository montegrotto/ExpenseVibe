import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from absence.models import AbsenceEntry, AbsenceType, Period, TimeReport, WorkSchedule
from accounts.models import CustomUser
from attachments.models import Attachment
from expenses.models import Category, Expense
from export.models import ExportBatch
from export.services import build_tlu_export
from mileage.models import MileageRate, MileageReport


def _fake_receipt_png():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("kvitto.png", buffer.read(), content_type="image/png")


class BuildTluExportTests(TestCase):
    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="EMP-42", first_name="Anna",
            last_name="Andersson",
        )
        self.category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        self.expense = Expense.objects.create(
            employee=self.employee, attachment=attachment, category=self.category, description="Tågbiljett",
            expense_date=date(2026, 2, 3), amount="245.50", vat_amount="49.10",
        )
        self.rate = MileageRate.objects.create(
            amount_per_km="25.00", export_code="050", export_code_name="Bilersättning (km)", valid_from=date(2026, 1, 1)
        )
        self.report = MileageReport(
            employee=self.employee, date=date(2026, 2, 5), start_location="Kontoret", end_location="Kunden",
            purpose="Kundmöte", distance_km="12.0",
        )
        self.report.recalculate_compensation()
        self.report.save()

    def test_groups_both_row_types_under_one_employee(self):
        xml_bytes = build_tlu_export([self.expense], [self.report])
        root = ET.fromstring(xml_bytes)
        employees = root.findall(".//Employee")
        self.assertEqual(len(employees), 1)
        self.assertEqual(employees[0].get("EmploymentNo"), "EMP-42")
        regoutlays = employees[0].findall("./RegOutlays/RegOutlay")
        self.assertEqual(len(regoutlays), 2)

    def test_expense_regoutlay_attributes(self):
        """OutlayType/NoOfPrivate/Unit/SumOfPrivateTax/InternNote är enligt
        Vismas spec obligatoriska attribut på varje RegOutlay som
        förekommer (fast värdet får vara tomt) - saknas attributet helt
        avvisar Visma filen, se export/services.py."""
        xml_bytes = build_tlu_export([self.expense], [])
        root = ET.fromstring(xml_bytes)
        regoutlay = root.find(".//RegOutlay")
        self.assertEqual(regoutlay.get("DateOfReport"), "2026-02-03")
        self.assertEqual(regoutlay.get("OutlayCode"), "RES")
        self.assertEqual(regoutlay.get("OutlayCodeName"), "Resor")
        self.assertEqual(regoutlay.get("OutlayType"), "RES - Resor")
        self.assertEqual(regoutlay.get("NoOfPrivate"), "")
        self.assertEqual(regoutlay.get("Unit"), "")
        self.assertEqual(regoutlay.get("SumOfPrivate"), "245.50")
        self.assertEqual(regoutlay.get("SumOfPrivateTax"), "49.10")
        self.assertEqual(regoutlay.get("InternNote"), "Utlägg")

    def test_mileage_regoutlay_attributes(self):
        xml_bytes = build_tlu_export([], [self.report])
        root = ET.fromstring(xml_bytes)
        regoutlay = root.find(".//RegOutlay")
        self.assertEqual(regoutlay.get("Unit"), "km")
        self.assertEqual(regoutlay.get("OutlayCode"), "050")
        self.assertEqual(regoutlay.get("OutlayType"), "050 - Bilersättning (km)")
        self.assertEqual(regoutlay.get("NoOfPrivate"), "12.0")
        self.assertEqual(regoutlay.get("PricePerUnit"), "25.00")
        self.assertEqual(regoutlay.get("SumOfPrivate"), "300.00")
        self.assertEqual(regoutlay.get("SumOfPrivateTax"), "")

    def test_regoutlaycodes_catalog_declares_used_codes_once(self):
        """Visma uppdaterar sitt utläggsregister från RegOutlayCodes - utan
        katalogen hanteras egentillagda utläggskoder inte korrekt vid
        importen. Ordningen TimeCodes, RegOutlayCodes, SalaryDataEmployee
        är specens."""
        second = Expense.objects.create(
            employee=self.employee, attachment=Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee),
            category=self.category, description="Buss", expense_date=date(2026, 2, 4), amount="30.00",
        )
        xml_bytes = build_tlu_export([self.expense, second], [self.report])
        root = ET.fromstring(xml_bytes)
        self.assertEqual([c.tag for c in root], ["TimeCodes", "RegOutlayCodes", "SalaryDataEmployee"])
        codes = root.findall("./RegOutlayCodes/RegOutlayCode")
        self.assertEqual(
            [(c.get("Code"), c.get("RegOutlayCodeName")) for c in codes],
            [("050", "Bilersättning (km)"), ("RES", "Resor")],
        )

    def test_root_declares_export_version(self):
        """Utan ExportVersion tolkar Visma filen som format 1.0 och
        ignorerar RegOutlayCodes/PricePerUnit - koderna plockas aldrig upp."""
        root = ET.fromstring(build_tlu_export([self.expense], []))
        self.assertEqual(root.get("ExportVersion"), "1.4")
        self.assertEqual(root.get("ProgramName"), "ExpenseVibe")
        self.assertEqual(root.get("BookDistributionProject"), "0")
        self.assertEqual(root.get("BookDistributionResultUnit"), "0")
        self.assertIsNone(root.get("OrgNo"))

    def test_regoutlaycodes_omitted_when_no_codes(self):
        self.report.mileage_rate = None
        xml_bytes = build_tlu_export([], [self.report])
        self.assertIsNone(ET.fromstring(xml_bytes).find("./RegOutlayCodes"))

    def test_declares_iso_8859_1_encoding(self):
        xml_bytes = build_tlu_export([self.expense], [])
        self.assertIn(b"encoding='ISO-8859-1'", xml_bytes)

    def test_salary_data_employee_always_declares_a_period(self):
        """Visma svarar "Felaktig period" om SalaryDataEmployee saknar
        FromDate/ToDate helt - måste alltid sättas, även utan att admin
        angett ett datumfilter på exportsidan."""
        xml_bytes = build_tlu_export([self.expense], [self.report])
        wrapper = ET.fromstring(xml_bytes).find(".//SalaryDataEmployee")
        self.assertEqual(wrapper.get("FromDate"), "2026-02-03")
        self.assertEqual(wrapper.get("ToDate"), "2026-02-05")

    def test_employee_from_date_reflects_actual_dates_not_typed_filter(self):
        """FromDate på Employee-elementet är personens FAKTISKA första
        datum, aldrig admins fria datumfilter rakt av. ToDate vidgas bara
        till period_to eftersom lönearterna rapporteras på sista dagen i
        perioden (se MergedRegOutlayTests)."""
        xml_bytes = build_tlu_export(
            [self.expense], [self.report], period_from=date(2026, 1, 1), period_to=date(2026, 12, 31)
        )
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        self.assertEqual(employee_el.get("FromDate"), "2026-02-03")
        self.assertEqual(employee_el.get("ToDate"), "2026-12-31")


class ExportCreateViewTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com", password="pw12345678", employment_number="1", is_admin=True
        )
        self.admin.must_change_password = False
        self.admin.save()
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="2"
        )
        self.category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        self.expense = Expense.objects.create(
            employee=self.employee, attachment=attachment, category=self.category, description="Tågbiljett",
            expense_date=date(2026, 2, 3), amount="245.50",
        )
        self.expense.approve(self.admin)
        self.client = Client()
        self.client.login(username="admin@example.com", password="pw12345678")

    def test_non_admin_forbidden(self):
        self.client.logout()
        self.employee.must_change_password = False
        self.employee.save()
        self.client.login(username="anna@example.com", password="pw12345678")
        response = self.client.get(reverse("export:export_create"))
        self.assertEqual(response.status_code, 403)

    def test_export_marks_items_exported_and_prevents_reexport(self):
        response = self.client.post(reverse("export:export_create"), {"expense_ids": [self.expense.pk]})
        self.assertEqual(response.status_code, 302)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, "exported")
        self.assertIsNotNone(self.expense.export_batch)
        batch = ExportBatch.objects.get()
        self.assertEqual(batch.expense_count, 1)
        self.assertTrue(batch.file)

        # Ett andra exportförsök ska inte hitta samma rad igen.
        second_response = self.client.get(reverse("export:export_create"))
        self.assertNotContains(second_response, "Tågbiljett")

    def test_download_returns_file(self):
        self.client.post(reverse("export:export_create"), {"expense_ids": [self.expense.pk]})
        batch = ExportBatch.objects.get()
        response = self.client.get(reverse("export:export_download", args=[batch.pk]))
        self.assertEqual(response.status_code, 200)


class BuildTluExportAbsenceTests(TestCase):
    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="EMP-42", first_name="Anna",
            last_name="Andersson",
        )
        self.period = Period.objects.create(month=date(2026, 3, 1))
        self.sick = AbsenceType.objects.create(
            name="Sjukdom", export_code="801", granularity=AbsenceType.Granularity.HOURS
        )
        self.vacation = AbsenceType.objects.create(
            name="Semester", export_code="802", granularity=AbsenceType.Granularity.WHOLE_DAY
        )

    def test_times_block_built_for_absence_entries(self):
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        root = ET.fromstring(xml_bytes)
        employee_el = root.find(".//Employee")
        self.assertEqual(employee_el.get("EmploymentNo"), "EMP-42")
        # Times är ett syskon till RegOutlays, inte en RegOutlay-variant.
        self.assertIsNone(employee_el.find("./RegOutlays/RegOutlay"))
        time_el = employee_el.find("./Times/Time")
        self.assertEqual(time_el.get("DateOfReport"), "2026-03-10")
        self.assertEqual(time_el.get("TimeCode"), "802")
        self.assertEqual(time_el.get("SumOfHours"), "8.00")

    def test_times_sorted_by_date_not_creation_order(self):
        """Vismas spec kräver att Time-raderna "ligger sorterade efter
        datum och tidkod" - AbsenceEntry.Meta.ordering ("-date") får inte
        läcka igenom till exporten i omvänd ordning."""
        later = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 20), absence_type=self.sick,
            hours=Decimal("4.00"),
        )
        later.full_clean()
        later.save()
        earlier = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        earlier.full_clean()
        earlier.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        times = ET.fromstring(xml_bytes).findall(".//Employee/Times/Time")
        self.assertEqual([t.get("DateOfReport") for t in times], ["2026-03-05", "2026-03-20"])

    def test_split_absence_entries_same_day_merged_into_one_time_row(self):
        """Vismas spec kräver att varje (datum, tidkod)-kombination är
        unik i Times. AbsenceEntry tillåter medvetet flera poster samma
        datum+frånvaroart (t.ex. delad vård av barn, se AbsenceEntry-
        docstringen) - exporten måste slå ihop dem till en rad med
        summerade timmar istället för att skriva ut en dubblett."""
        morning = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.sick,
            hours=Decimal("3.00"),
        )
        morning.full_clean()
        morning.save()
        afternoon = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.sick,
            hours=Decimal("4.00"),
        )
        afternoon.full_clean()
        afternoon.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        times = ET.fromstring(xml_bytes).findall(".//Employee/Times/Time")
        self.assertEqual(len(times), 1)
        self.assertEqual(times[0].get("DateOfReport"), "2026-03-10")
        self.assertEqual(times[0].get("TimeCode"), "801")
        self.assertEqual(times[0].get("SumOfHours"), "7.00")

    def test_time_code_and_sum_of_hours_never_omitted(self):
        """TimeCode/SumOfHours är enligt Vismas spec obligatoriska attribut
        på Time - får vara tomma, men får inte utelämnas helt. En AbsenceType
        utan export_code (fältet tillåter blankt) ska alltså fortfarande ge
        ett TimeCode-attribut (tomt), inte ett Time-element utan attributet."""
        no_code_type = AbsenceType.objects.create(
            name="Ospecificerad", export_code="", granularity=AbsenceType.Granularity.HOURS
        )
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=no_code_type,
            hours=Decimal("4.00"),
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        time_el = ET.fromstring(xml_bytes).find(".//Employee/Times/Time")
        self.assertEqual(time_el.get("TimeCode"), "")
        self.assertEqual(time_el.get("SumOfHours"), "4.00")

    def test_time_adjustments_and_balances_present_but_empty(self):
        """TimeAdjustments/TimeBalances är enligt spec obligatoriska
        syskonelement till NormalWorkingTimes/Times så fort Employee har
        någon tidrapportering - vi använder inga saldon/justeringar, men
        elementen måste ändå skrivas ut (tomma)."""
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        self.assertIsNotNone(employee_el.find("./TimeAdjustments"))
        self.assertIsNotNone(employee_el.find("./TimeBalances"))
        self.assertEqual(len(employee_el.find("./TimeAdjustments")), 0)
        self.assertEqual(len(employee_el.find("./TimeBalances")), 0)

    def test_employee_child_element_order_matches_genuine_export(self):
        """En genuin Timeplan-export ordnar Employees syskonelement
        NormalWorkingTimes, Times, TimeAdjustments, TimeBalances, RegOutlays
        - RegOutlays sist, aldrig först. Osäkert om Visma faktiskt kräver
        exakt den ordningen, men vi matchar den rakt av istället för att
        gissa vilka avsteg som är ofarliga."""
        category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        expense = Expense.objects.create(
            employee=self.employee, category=category, attachment=attachment, amount=Decimal("100.00"),
            expense_date=date(2026, 3, 10), description="Taxi",
        )
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([expense], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        children = [child.tag for child in employee_el]
        self.assertEqual(
            children, ["NormalWorkingTimes", "Times", "TimeAdjustments", "TimeBalances", "RegOutlays"]
        )

    def test_normal_working_times_covers_full_employee_period(self):
        """Utan detta svarar Visma "Normalarbetstid saknas eller har fel
        format i filen" - måste finnas en rad per kalenderdag med
        schemalagd arbetstid i personens deklarerade period (dagar utan
        schemalagd tid, som helger, hoppas över helt - se
        test_normal_working_times_skips_days_without_scheduled_hours)."""
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        normal_times = employee_el.findall("./NormalWorkingTimes/NormalWorkingTime")
        self.assertEqual(len(normal_times), 22)  # vardagarna i mars, personens period
        by_date = {el.get("DateOfReport"): el.get("NormalWorkingTimeHours") for el in normal_times}
        self.assertEqual(by_date["2026-03-02"], "8.00")  # måndag
        self.assertEqual(by_date["2026-03-31"], "8.00")  # tisdag

        # FlexTimeHours måste finnas på varje NormalWorkingTime (tomt är
        # okej) - saknas attributet helt svarar Visma "Skillnad i
        # normalarbetstid i tid och löns schema", trots att
        # NormalWorkingTimeHours-värdena är korrekta. Se en genuin
        # Timeplan-export, där attributet alltid finns men alltid är tomt.
        for el in normal_times:
            self.assertEqual(el.get("FlexTimeHours"), "")

        # NormalWorkingTimes måste komma före Times under Employee.
        children = [child.tag for child in employee_el]
        self.assertLess(children.index("NormalWorkingTimes"), children.index("Times"))

    def test_normal_working_times_skips_days_without_scheduled_hours(self):
        """En genuin Timeplan-export hoppar helt över dagar utan
        schemalagd arbetstid (helger, helgdagar) istället för att skriva
        ut en 0.00-rad - det var den skillnaden mot en riktig export som
        fick Visma att avvisa vår fil."""
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        dates = {
            el.get("DateOfReport") for el in employee_el.findall("./NormalWorkingTimes/NormalWorkingTime")
        }
        self.assertNotIn("2026-03-01", dates)  # söndag
        self.assertNotIn("2026-03-07", dates)  # lördag

    def test_normal_working_times_uses_employees_own_schedule(self):
        schedule = WorkSchedule.get_for_employee(self.employee)
        schedule.monday_hours = Decimal("4.00")
        schedule.save()

        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        by_date = {
            el.get("DateOfReport"): el.get("NormalWorkingTimeHours")
            for el in employee_el.findall("./NormalWorkingTimes/NormalWorkingTime")
        }
        self.assertEqual(by_date["2026-03-02"], "4.00")  # måndag, deltid

    def test_normal_working_times_zero_on_holiday_falling_on_a_weekday(self):
        """Långfredagen 2026 är en fredag - ska hoppas över (inte visas som
        en 0.00-rad) trots att fredag annars är en schemalagd 8-timmarsdag."""
        april_period = Period.objects.create(month=date(2026, 4, 1))
        entry = AbsenceEntry(
            employee=self.employee, period=april_period, date=date(2026, 4, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=april_period)

        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        by_date = {
            el.get("DateOfReport"): el.get("NormalWorkingTimeHours")
            for el in employee_el.findall("./NormalWorkingTimes/NormalWorkingTime")
        }
        self.assertNotIn("2026-04-03", by_date)  # långfredagen, annars en fredag (8h)
        self.assertNotIn("2026-04-06", by_date)  # annandag påsk, annars en måndag (8h)
        self.assertEqual(by_date["2026-04-02"], "8.00")  # vanlig torsdag samma vecka

    def test_normal_working_times_zero_on_julafton_and_nyarsafton(self):
        december_period = Period.objects.create(month=date(2026, 12, 1))
        entry = AbsenceEntry(
            employee=self.employee, period=december_period, date=date(2026, 12, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=december_period)

        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        by_date = {
            el.get("DateOfReport"): el.get("NormalWorkingTimeHours")
            for el in employee_el.findall("./NormalWorkingTimes/NormalWorkingTime")
        }
        self.assertNotIn("2026-12-24", by_date)  # julafton, torsdag (annars 8h)
        self.assertNotIn("2026-12-25", by_date)  # juldagen, fredag (annars 8h)
        self.assertNotIn("2026-12-31", by_date)  # nyårsafton, torsdag (annars 8h)

    def test_normal_working_times_zero_on_midsommarafton(self):
        june_period = Period.objects.create(month=date(2026, 6, 1))
        entry = AbsenceEntry(
            employee=self.employee, period=june_period, date=date(2026, 6, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=june_period)

        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        by_date = {
            el.get("DateOfReport"): el.get("NormalWorkingTimeHours")
            for el in employee_el.findall("./NormalWorkingTimes/NormalWorkingTime")
        }
        self.assertNotIn("2026-06-19", by_date)  # midsommarafton, fredag (annars 8h)
        self.assertNotIn("2026-06-20", by_date)  # midsommardagen, lördag

    def test_normal_working_times_absent_without_absence_data(self):
        category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        expense = Expense.objects.create(
            employee=self.employee, attachment=attachment, category=category, description="Tågbiljett",
            expense_date=date(2026, 3, 3), amount="100.00",
        )
        xml_bytes = build_tlu_export([expense], [])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        self.assertIsNone(employee_el.find("./NormalWorkingTimes"))

    def test_empty_time_report_does_not_crash_and_uses_period_bounds(self):
        report = TimeReport.objects.create(employee=self.employee, period=self.period)
        xml_bytes = build_tlu_export([], [], [report])
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        self.assertEqual(employee_el.get("FromDate"), "2026-03-01")
        self.assertEqual(employee_el.get("ToDate"), "2026-03-31")
        self.assertIsNone(employee_el.find("./Times/Time"))

    def test_timecodes_catalog_declares_used_absence_types(self):
        """Utan detta svarar Visma "Importen av tidkoder misslyckades" -
        TimeCodes är obligatoriskt."""
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 10), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        root = ET.fromstring(xml_bytes)
        # TimeCodes måste vara ett syskon till SalaryDataEmployee under
        # SalaryData (i den ordningen), inte nästlat inuti den.
        children = list(root)
        self.assertEqual([child.tag for child in children], ["TimeCodes", "SalaryDataEmployee"])
        timecodes = children[0]
        codes = timecodes.findall("TimeCode")
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0].get("Code"), "802")
        self.assertEqual(codes[0].get("TimeCodeName"), "Semester")

    def test_timecodes_catalog_lists_each_used_code_once(self):
        AbsenceEntry.objects.create(
            employee=self.employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        AbsenceEntry.objects.create(
            employee=self.employee, period=self.period, date=date(2026, 3, 6), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([], [], [report])
        codes = ET.fromstring(xml_bytes).findall("./TimeCodes/TimeCode")
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0].get("Code"), "801")

    def test_timecodes_element_present_but_empty_without_absence(self):
        xml_bytes = build_tlu_export([], [])
        timecodes = ET.fromstring(xml_bytes).find("./TimeCodes")
        self.assertIsNotNone(timecodes)
        self.assertEqual(len(timecodes.findall("TimeCode")), 0)

    def test_mixed_expense_mileage_absence_grouped_under_one_employee(self):
        category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        expense = Expense.objects.create(
            employee=self.employee, attachment=attachment, category=category, description="Tågbiljett",
            expense_date=date(2026, 3, 3), amount="100.00",
        )
        rate = MileageRate.objects.create(amount_per_km="25.00", export_code="050", valid_from=date(2026, 1, 1))
        mileage_report = MileageReport(
            employee=self.employee, date=date(2026, 3, 4), start_location="Kontoret", end_location="Kunden",
            purpose="Möte", distance_km="10.0",
        )
        mileage_report.recalculate_compensation()
        mileage_report.save()

        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("4.00"),
        )
        entry.full_clean()
        entry.save()
        time_report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([expense], [mileage_report], [time_report])
        employees = ET.fromstring(xml_bytes).findall(".//Employee")
        self.assertEqual(len(employees), 1)
        self.assertEqual(len(employees[0].findall("./RegOutlays/RegOutlay")), 2)
        self.assertEqual(len(employees[0].findall("./Times/Time")), 1)

    def test_mixed_export_without_typed_date_filter_still_declares_batch_period(self):
        """Reproducerar felet från verklig Visma-import: en blandad export
        (utlägg + kilometer + frånvaro) där admin lämnat "period från/till"
        tomt på exportsidan gav "Felaktig period" eftersom
        SalaryDataEmployee helt saknade FromDate/ToDate i det fallet."""
        category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
        expense = Expense.objects.create(
            employee=self.employee, attachment=attachment, category=category, description="Tågbiljett",
            expense_date=date(2026, 3, 3), amount="100.00",
        )
        MileageRate.objects.create(amount_per_km="25.00", export_code="050", valid_from=date(2026, 1, 1))
        mileage_report = MileageReport(
            employee=self.employee, date=date(2026, 3, 4), start_location="Kontoret", end_location="Kunden",
            purpose="Möte", distance_km="10.0",
        )
        mileage_report.recalculate_compensation()
        mileage_report.save()

        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 20), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        time_report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export([expense], [mileage_report], [time_report], period_from=None, period_to=None)
        wrapper = ET.fromstring(xml_bytes).find(".//SalaryDataEmployee")
        self.assertIsNotNone(wrapper.get("FromDate"))
        self.assertIsNotNone(wrapper.get("ToDate"))
        self.assertEqual(wrapper.get("FromDate"), "2026-03-01")  # periodens start täcker in absence-posten
        self.assertEqual(wrapper.get("ToDate"), "2026-03-31")

    def test_batch_period_widens_to_cover_an_absence_period_outside_typed_filter(self):
        """Om admin filtrerar utläggen på ett datumintervall som INTE
        täcker en samtidigt vald frånvaroperiod ska SalaryDataEmployees
        period ändå vidgas att täcka allt - annars skulle Employee-
        elementets egna FromDate/ToDate (som alltid är de faktiska
        datumen) hamna utanför den deklarerade batch-perioden."""
        entry = AbsenceEntry(
            employee=self.employee, period=self.period, date=date(2026, 3, 20), absence_type=self.vacation
        )
        entry.full_clean()
        entry.save()
        time_report = TimeReport.objects.create(employee=self.employee, period=self.period)

        xml_bytes = build_tlu_export(
            [], [], [time_report], period_from=date(2026, 4, 1), period_to=date(2026, 4, 30)
        )
        wrapper = ET.fromstring(xml_bytes).find(".//SalaryDataEmployee")
        self.assertEqual(wrapper.get("FromDate"), "2026-03-01")
        self.assertEqual(wrapper.get("ToDate"), "2026-04-30")


class ExportCreateAbsencePeriodTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com", password="pw12345678", employment_number="1", is_admin=True
        )
        self.admin.must_change_password = False
        self.admin.save()
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="2"
        )
        self.other_employee = CustomUser.objects.create_user(
            email="bertil@example.com", password="pw12345678", employment_number="3"
        )
        self.period = Period.objects.create(month=date(2026, 3, 1))
        self.sick = AbsenceType.objects.create(
            name="Sjukdom", export_code="801", granularity=AbsenceType.Granularity.HOURS
        )
        self.client = Client()
        self.client.login(username="admin@example.com", password="pw12345678")

    def _approved_report_with_entry(self, employee):
        entry = AbsenceEntry(
            employee=employee, period=self.period, date=date(2026, 3, 5), absence_type=self.sick,
            hours=Decimal("4.00"),
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=employee, period=self.period)
        report.approve(self.admin)
        return report

    def test_export_marks_time_report_exported_and_closes_period(self):
        report = self._approved_report_with_entry(self.employee)
        response = self.client.post(reverse("export:export_create"), {"period_ids": [self.period.pk]})
        self.assertEqual(response.status_code, 302)

        report.refresh_from_db()
        self.assertEqual(report.status, "exported")
        self.assertIsNotNone(report.export_batch)

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, Period.PeriodStatus.REPORTED)
        self.assertIsNotNone(self.period.reported_at)

        batch = ExportBatch.objects.get()
        self.assertEqual(batch.time_report_count, 1)

    def test_period_stays_open_when_another_employees_report_still_pending(self):
        report = self._approved_report_with_entry(self.employee)

        pending_entry = AbsenceEntry(
            employee=self.other_employee, period=self.period, date=date(2026, 3, 6), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        pending_entry.full_clean()
        pending_entry.save()
        TimeReport.objects.create(employee=self.other_employee, period=self.period)  # still submitted, not approved

        self.client.post(reverse("export:export_create"), {"period_ids": [self.period.pk]})

        report.refresh_from_db()
        self.assertEqual(report.status, "exported")

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, Period.PeriodStatus.OPEN)

    def test_rejected_report_does_not_block_period_closing(self):
        report = self._approved_report_with_entry(self.employee)

        other_entry = AbsenceEntry(
            employee=self.other_employee, period=self.period, date=date(2026, 3, 6), absence_type=self.sick,
            hours=Decimal("2.00"),
        )
        other_entry.full_clean()
        other_entry.save()
        other_report = TimeReport.objects.create(employee=self.other_employee, period=self.period)
        other_report.reject(self.admin, "Fel timmar")

        self.client.post(reverse("export:export_create"), {"period_ids": [self.period.pk]})

        report.refresh_from_db()
        self.assertEqual(report.status, "exported")

        self.period.refresh_from_db()
        self.assertEqual(self.period.status, Period.PeriodStatus.REPORTED)


class NormalWorkingTimeRangeTests(TestCase):
    """Regressionstest: NormalWorkingTimes ska bara täcka tidrapporternas
    period - inte vidgas av orelaterade utlägg/kilometer i samma batch
    (Employee FromDate/ToDate ska däremot täcka allt)."""

    def test_unrelated_expense_does_not_widen_normal_working_times(self):
        employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="EMP-42", first_name="Anna",
            last_name="Andersson",
        )
        period = Period.objects.create(month=date(2026, 3, 1))
        sick = AbsenceType.objects.create(
            name="Sjukdom", export_code="801", granularity=AbsenceType.Granularity.HOURS
        )
        entry = AbsenceEntry(
            employee=employee, period=period, date=date(2026, 3, 10), absence_type=sick, hours=Decimal("4.00")
        )
        entry.full_clean()
        entry.save()
        report = TimeReport.objects.create(employee=employee, period=period)

        category = Category.objects.create(name="Resor", code="RES")
        attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=employee)
        expense = Expense.objects.create(
            employee=employee,
            attachment=attachment,
            category=category,
            description="Tågbiljett",
            expense_date=date(2026, 1, 5),
            amount="45.00",
        )

        xml_bytes = build_tlu_export([expense], [], [report])
        root = ET.fromstring(xml_bytes)
        employee_el = root.find(".//Employee")
        # Employee-perioden täcker även utlägget ...
        self.assertEqual(employee_el.get("FromDate"), "2026-01-05")
        self.assertEqual(employee_el.get("ToDate"), "2026-03-31")
        # ... men NormalWorkingTimes håller sig inom tidrapportens månad.
        nwt_dates = [
            el.get("DateOfReport") for el in employee_el.findall("./NormalWorkingTimes/NormalWorkingTime")
        ]
        self.assertTrue(nwt_dates)
        self.assertTrue(all(d.startswith("2026-03-") for d in nwt_dates), nwt_dates)


class MergedRegOutlayTests(TestCase):
    """Lönearter levereras inte dag för dag utan summeras per anställd och
    OutlayCode och rapporteras på sista dagen i perioden."""

    def setUp(self):
        self.employee = CustomUser.objects.create_user(
            email="anna@example.com", password="pw12345678", employment_number="EMP-42", first_name="Anna",
        )
        self.category = Category.objects.create(name="Resor", code="RES")
        self.expenses = []
        for day, amount, vat, note in [(3, "100.00", "20.00", "Tåg"), (10, "50.50", None, "Buss")]:
            attachment = Attachment.objects.create(file=_fake_receipt_png(), uploaded_by=self.employee)
            self.expenses.append(Expense.objects.create(
                employee=self.employee, attachment=attachment, category=self.category, description=note,
                expense_date=date(2026, 2, day), amount=amount, vat_amount=vat,
            ))
        rate = MileageRate.objects.create(
            amount_per_km="25.00", export_code="050", export_code_name="Bil", valid_from=date(2026, 1, 1)
        )
        self.reports = []
        for day, km in [(5, "12.0"), (20, "8.0")]:
            r = MileageReport(
                employee=self.employee, date=date(2026, 2, day), start_location="A", end_location="B",
                purpose="Kund", distance_km=km,
            )
            r.recalculate_compensation()
            r.save()
            self.reports.append(r)

    def test_one_row_per_code_dated_last_day_of_period(self):
        xml_bytes = build_tlu_export(self.expenses, self.reports, period_to=date(2026, 2, 28))
        employee_el = ET.fromstring(xml_bytes).find(".//Employee")
        rows = {el.get("OutlayCode"): el for el in employee_el.findall("./RegOutlays/RegOutlay")}
        self.assertEqual(set(rows), {"RES", "050"})
        self.assertEqual(rows["RES"].get("DateOfReport"), "2026-02-28")
        self.assertEqual(rows["RES"].get("SumOfPrivate"), "150.50")
        self.assertEqual(rows["RES"].get("SumOfPrivateTax"), "20.00")
        self.assertEqual(rows["050"].get("InternNote"), "Utlägg")
        self.assertEqual(rows["RES"].get("InternNote"), "")
        self.assertEqual(rows["050"].get("NoOfPrivate"), "20.0")
        self.assertEqual(rows["050"].get("SumOfPrivate"), "500.00")
        self.assertEqual(rows["050"].get("PricePerUnit"), "25.00")
        self.assertEqual(employee_el.get("ToDate"), "2026-02-28")

    def test_without_period_filter_uses_employees_last_date(self):
        xml_bytes = build_tlu_export(self.expenses, [])
        row = ET.fromstring(xml_bytes).find(".//RegOutlay")
        self.assertEqual(row.get("DateOfReport"), "2026-02-10")
