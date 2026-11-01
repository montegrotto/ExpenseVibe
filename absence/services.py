from absence.models import Period, TimeReport
from core.models import ApprovalStatus


def open_period(month):
    """Skapar och öppnar perioden för `month` (tvingas till dag 1 av
    Period.save()) om den inte redan finns. Idempotent - säker att anropa
    upprepade gånger för samma månad. Delas mellan management-kommandot
    open_period (tänkt körd via extern cron) och adminvyn absence:period_open
    (manuell fallback/backfill)."""
    return Period.objects.get_or_create(month=month.replace(day=1), defaults={"status": Period.PeriodStatus.OPEN})


def submit_time_report(employee, month):
    """"Markera som färdig" för `employee`s tidrapport för `month`. Returnerar
    (nivå, meddelande) där nivå är "success", "info" eller "error" - samma
    namn som django.contrib.messages. Delas mellan absence:timereport_submit
    och api.views.absence_submit."""
    period = Period.objects.filter(month=month).first()
    if period is None or not period.is_open:
        return "error", "Perioden är inte öppen."
    report = TimeReport.objects.filter(employee=employee, period=period).first()
    if report is None:
        TimeReport.objects.create(employee=employee, period=period)
        return "success", "Tidrapporten är inskickad för attestering."
    if report.status == ApprovalStatus.REJECTED:
        report.resubmit()
        return "success", "Tidrapporten är inskickad på nytt för attestering."
    if report.status == ApprovalStatus.SUBMITTED:
        return "info", "Tidrapporten är redan inskickad."
    return "error", "Tidrapporten kan inte längre skickas in."
