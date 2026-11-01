import calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from absence.forms import AbsenceEntryForm, AbsenceSettingsForm, AbsenceTypeForm, WorkScheduleForm
from absence.holidays import non_working_day_name
from absence.models import AbsenceEntry, AbsenceSettings, AbsenceType, Period, TimeReport, WorkSchedule
from absence.services import open_period, submit_time_report
from accounts.models import CustomUser
from core.decorators import admin_required
from core.models import ApprovalStatus


def _parse_month(value):
    if not value:
        return None
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, TypeError):
        return None


def _shift_month(month, delta):
    index = month.year * 12 + (month.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def _resolve_period(entry_date):
    return Period.objects.filter(month=entry_date.replace(day=1)).first()


def _calendar_url(month):
    return f"{reverse('absence:absence_calendar')}?month={month.strftime('%Y-%m')}"


def save_entry(form, employee=None):
    """Sparar ett validerat AbsenceEntryForm: kopplar perioden utifrån
    datumet och kör modellvalideringen. Returnerar posten, eller None med
    felen lagda på formuläret. Delas med api.views.absence."""
    entry = form.save(commit=False)
    if employee is not None:
        entry.employee = employee
    period = _resolve_period(entry.date) if entry.date else None
    if period is None:
        form.add_error("date", "Perioden är inte öppnad ännu.")
        return None
    entry.period = period
    try:
        entry.full_clean()
    except ValidationError as exc:
        form.add_error(None, exc)
        return None
    entry.save()
    return entry


@login_required
def absence_calendar(request):
    today = timezone.localdate()
    month = _parse_month(request.GET.get("month")) or today.replace(day=1)

    period = Period.objects.filter(month=month).first()
    time_report = TimeReport.objects.filter(employee=request.user, period=period).first() if period else None
    entries = (
        AbsenceEntry.objects.filter(employee=request.user, period=period)
        .select_related("absence_type")
        .order_by("date")
        if period
        else AbsenceEntry.objects.none()
    )

    entries_by_day = {}
    for entry in entries:
        entries_by_day.setdefault(entry.date.day, []).append(entry)

    can_edit = bool(period and period.is_reportable_for(request.user))
    can_submit = bool(period and period.is_open and (time_report is None or time_report.status == ApprovalStatus.REJECTED))
    absence_settings = AbsenceSettings.get_solo()

    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(month.year, month.month):
        cells = []
        for day_number in week:
            if day_number == 0:
                cells.append(None)
            else:
                cell_date = date(month.year, month.month, day_number)
                cells.append(
                    {
                        "day": day_number,
                        "date": cell_date,
                        "is_today": cell_date == today,
                        "entries": entries_by_day.get(day_number, []),
                        "blocked": absence_settings.blocks_date(cell_date),
                        "holiday_name": non_working_day_name(cell_date),
                    }
                )
        weeks.append(cells)

    return render(
        request,
        "absence/absence_calendar.html",
        {
            "month": month,
            "weeks": weeks,
            "period": period,
            "time_report": time_report,
            "can_edit": can_edit,
            "can_submit": can_submit,
            "prev_month": _shift_month(month, -1).strftime("%Y-%m"),
            "next_month": _shift_month(month, 1).strftime("%Y-%m"),
        },
    )


@login_required
def absenceentry_create(request):
    initial = {}
    date_param = request.GET.get("date")
    if date_param:
        initial["date"] = date_param

    if request.method == "POST":
        form = AbsenceEntryForm(request.POST)
        entry = save_entry(form, request.user) if form.is_valid() else None
        if entry is not None:
            messages.success(request, "Frånvaroposten är sparad.")
            return redirect(_calendar_url(entry.date.replace(day=1)))
    else:
        form = AbsenceEntryForm(initial=initial)
    return render(request, "absence/absenceentry_form.html", {"form": form, "title": "Ny frånvaropost"})


@login_required
def absenceentry_edit(request, pk):
    entry = get_object_or_404(AbsenceEntry, pk=pk, employee=request.user)
    if request.method == "POST":
        form = AbsenceEntryForm(request.POST, instance=entry)
        updated = save_entry(form) if form.is_valid() else None
        if updated is not None:
            messages.success(request, "Frånvaroposten är uppdaterad.")
            return redirect(_calendar_url(updated.date.replace(day=1)))
    else:
        form = AbsenceEntryForm(instance=entry)
    return render(
        request, "absence/absenceentry_form.html", {"form": form, "entry": entry, "title": "Redigera frånvaropost"}
    )


@login_required
def absenceentry_delete(request, pk):
    entry = get_object_or_404(AbsenceEntry, pk=pk, employee=request.user)
    redirect_url = _calendar_url(entry.date.replace(day=1))
    if request.method == "POST":
        if not entry.period.is_reportable_for(request.user):
            messages.error(request, "Perioden är inte längre öppen för ändringar.")
        else:
            entry.delete()
            messages.success(request, "Frånvaroposten är borttagen.")
        return redirect(redirect_url)
    return render(request, "absence/absenceentry_delete_confirm.html", {"entry": entry})


@login_required
def timereport_submit(request):
    if request.method != "POST":
        return redirect("absence:absence_calendar")

    month = _parse_month(request.POST.get("month"))
    if month is None:
        return redirect("absence:absence_calendar")

    level, text = submit_time_report(request.user, month)
    getattr(messages, level)(request, text)
    return redirect(_calendar_url(month))


@login_required
def timereport_list(request):
    reports = TimeReport.visible_to(request.user).select_related("employee", "period")
    return render(request, "absence/timereport_list.html", {"reports": reports})


@login_required
def timereport_detail(request, pk):
    report = get_object_or_404(TimeReport.visible_to(request.user), pk=pk)
    return render(request, "absence/timereport_detail.html", {"report": report, "entries": report.entries})


@admin_required
def absencetype_list(request):
    types = AbsenceType.objects.all()
    return render(request, "absence/absencetype_list.html", {"types": types})


@admin_required
def absencetype_create(request):
    if request.method == "POST":
        form = AbsenceTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Frånvaroarten är skapad.")
            return redirect("absence:absencetype_list")
    else:
        form = AbsenceTypeForm()
    return render(request, "absence/absencetype_form.html", {"form": form, "title": "Ny frånvaroart"})


@admin_required
def absencetype_edit(request, pk):
    absence_type = get_object_or_404(AbsenceType, pk=pk)
    if request.method == "POST":
        form = AbsenceTypeForm(request.POST, instance=absence_type)
        if form.is_valid():
            form.save()
            messages.success(request, "Frånvaroarten är uppdaterad.")
            return redirect("absence:absencetype_list")
    else:
        form = AbsenceTypeForm(instance=absence_type)
    return render(
        request, "absence/absencetype_form.html", {"form": form, "title": f"Redigera {absence_type.name}"}
    )


@admin_required
def absencetype_delete(request, pk):
    absence_type = get_object_or_404(AbsenceType, pk=pk)
    if request.method == "POST":
        if absence_type.can_delete:
            absence_type.delete()
            messages.success(request, "Frånvaroarten är borttagen.")
        else:
            absence_type.is_active = False
            absence_type.save(update_fields=["is_active"])
            messages.info(
                request, "Frånvaroarten har kopplade poster och kunde inte tas bort - den är inaktiverad istället."
            )
        return redirect("absence:absencetype_list")
    return render(request, "absence/absencetype_delete_confirm.html", {"absence_type": absence_type})


@admin_required
def period_list(request):
    periods = Period.objects.all()
    return render(request, "absence/period_list.html", {"periods": periods})


@admin_required
def period_open(request):
    if request.method == "POST":
        month = _parse_month(request.POST.get("month"))
        if month is None:
            messages.error(request, "Ogiltig månad.")
        else:
            period, created = open_period(month)
            if created:
                messages.success(request, f"Perioden {period} är öppnad.")
            else:
                messages.info(request, f"Perioden {period} finns redan.")
    return redirect("absence:period_list")


@admin_required
def period_reopen(request, pk):
    period = get_object_or_404(Period, pk=pk)
    if request.method == "POST":
        if period.status == Period.PeriodStatus.REPORTED:
            period.status = Period.PeriodStatus.OPEN
            period.reported_at = None
            period.save(update_fields=["status", "reported_at"])
            messages.success(request, f"Perioden {period} är återöppnad.")
        return redirect("absence:period_list")
    return render(request, "absence/period_reopen_confirm.html", {"period": period})


@admin_required
def absencesettings_edit(request):
    settings_obj = AbsenceSettings.get_solo()
    if request.method == "POST":
        form = AbsenceSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            settings_obj = form.save(commit=False)
            settings_obj.updated_by = request.user
            settings_obj.save()
            messages.success(request, "Inställningen är sparad.")
            return redirect("absence:absencesettings_edit")
    else:
        form = AbsenceSettingsForm(instance=settings_obj)
    return render(request, "absence/absencesettings_form.html", {"form": form, "title": "Inställningar"})


@admin_required
def workschedule_list(request):
    employees = CustomUser.objects.filter(is_active=True)
    schedules = {schedule.employee_id: schedule for schedule in WorkSchedule.objects.all()}
    rows = [(employee, schedules.get(employee.pk)) for employee in employees]
    return render(request, "absence/workschedule_list.html", {"rows": rows})


@admin_required
def workschedule_edit(request, pk):
    employee = get_object_or_404(CustomUser, pk=pk)
    schedule = WorkSchedule.get_for_employee(employee)
    if request.method == "POST":
        form = WorkScheduleForm(request.POST, instance=schedule)
        if form.is_valid():
            form.save()
            messages.success(request, f"Arbetsschemat för {employee} är sparat.")
            return redirect("absence:workschedule_list")
    else:
        form = WorkScheduleForm(instance=schedule)
    return render(
        request, "absence/workschedule_form.html", {"form": form, "employee": employee, "title": f"Arbetsschema – {employee}"}
    )
