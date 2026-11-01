from datetime import datetime

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from absence.models import Period, TimeReport
from core.decorators import admin_required
from core.models import ApprovalStatus
from expenses.models import Expense
from export.models import ExportBatch
from export.services import build_tlu_export
from mileage.models import MileageReport


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@admin_required
def export_create(request):
    period_from = _parse_date(request.GET.get("period_from") or request.POST.get("period_from"))
    period_to = _parse_date(request.GET.get("period_to") or request.POST.get("period_to"))

    expense_qs = Expense.objects.filter(status="approved", export_batch__isnull=True).select_related(
        "employee", "category"
    )
    mileage_qs = MileageReport.objects.filter(status="approved", export_batch__isnull=True).select_related("employee")
    if period_from:
        expense_qs = expense_qs.filter(expense_date__gte=period_from)
        mileage_qs = mileage_qs.filter(date__gte=period_from)
    if period_to:
        expense_qs = expense_qs.filter(expense_date__lte=period_to)
        mileage_qs = mileage_qs.filter(date__lte=period_to)

    # Frånvaro väljs periodvis, inte i det fria period_from/period_to-
    # datumfiltret ovan - låsningen (öppen→rapporterad) är periodgranulär,
    # se export_create's POST-hantering nedan.
    pending_time_report_filter = Q(time_reports__status=ApprovalStatus.APPROVED, time_reports__export_batch__isnull=True)
    periods_qs = (
        Period.objects.filter(pending_time_report_filter)
        .annotate(pending_time_report_count=Count("time_reports", filter=pending_time_report_filter))
        .distinct()
    )

    if request.method == "POST":
        # isdigit-filtret gör att en manipulerad/trasig POST-body ("abc",
        # tom sträng) ignoreras istället för att ge ValueError/500.
        selected_expense_ids = {int(pk) for pk in request.POST.getlist("expense_ids") if pk.isdigit()}
        selected_mileage_ids = {int(pk) for pk in request.POST.getlist("mileage_ids") if pk.isdigit()}
        selected_period_ids = {int(pk) for pk in request.POST.getlist("period_ids") if pk.isdigit()}
        expenses = list(expense_qs.filter(pk__in=selected_expense_ids)) if selected_expense_ids else []
        mileage_reports = list(mileage_qs.filter(pk__in=selected_mileage_ids)) if selected_mileage_ids else []
        time_reports = (
            list(
                TimeReport.objects.filter(
                    period_id__in=selected_period_ids,
                    status=ApprovalStatus.APPROVED,
                    export_batch__isnull=True,
                ).select_related("employee", "period")
            )
            if selected_period_ids
            else []
        )

        if not expenses and not mileage_reports and not time_reports:
            messages.error(request, "Inga rader valda för export.")
            return redirect("export:export_create")

        with transaction.atomic():
            locked_expense_ids = list(
                Expense.objects.select_for_update()
                .filter(pk__in=[e.pk for e in expenses], status="approved", export_batch__isnull=True)
                .values_list("pk", flat=True)
            )
            locked_mileage_ids = list(
                MileageReport.objects.select_for_update()
                .filter(pk__in=[m.pk for m in mileage_reports], status="approved", export_batch__isnull=True)
                .values_list("pk", flat=True)
            )
            locked_time_report_ids = list(
                TimeReport.objects.select_for_update()
                .filter(pk__in=[t.pk for t in time_reports], status=ApprovalStatus.APPROVED, export_batch__isnull=True)
                .values_list("pk", flat=True)
            )
            expenses = [e for e in expenses if e.pk in locked_expense_ids]
            mileage_reports = [m for m in mileage_reports if m.pk in locked_mileage_ids]
            time_reports = [t for t in time_reports if t.pk in locked_time_report_ids]

            if not expenses and not mileage_reports and not time_reports:
                messages.error(request, "De valda raderna hann exporteras av någon annan. Försök igen.")
                return redirect("export:export_create")

            file_bytes = build_tlu_export(expenses, mileage_reports, time_reports, period_from, period_to)
            total = sum(e.amount for e in expenses) + sum(m.compensation_amount for m in mileage_reports)

            batch = ExportBatch.objects.create(
                created_by=request.user,
                period_from=period_from,
                period_to=period_to,
                expense_count=len(expenses),
                mileage_count=len(mileage_reports),
                time_report_count=len(time_reports),
                total_amount=total,
            )
            batch.file.save(f"utlagg_{batch.pk}.tlu", ContentFile(file_bytes), save=True)

            for expense in expenses:
                expense.mark_exported(batch)
            for report in mileage_reports:
                report.mark_exported(batch)

            affected_period_ids = set()
            for time_report in time_reports:
                time_report.mark_exported(batch)
                affected_period_ids.add(time_report.period_id)

            # Perioden stängs (rapporterad) bara om inga oattesterade
            # tidrapporter återstår för den - annars skulle en admin som
            # exporterar tidigt permanent kunna stänga ute anställda som
            # inte hunnit lämna in än. Avvisade tidrapporter räknas inte
            # som "kvarvarande" (de blockerar inte stängning) - se
            # absence:period_reopen för den medvetna undantagsvägen om en
            # sådan rättas och behöver skickas in efter att perioden redan
            # stängts.
            for period in Period.objects.select_for_update().filter(pk__in=affected_period_ids):
                still_pending = TimeReport.objects.filter(period=period, status=ApprovalStatus.SUBMITTED).exists()
                if not still_pending:
                    period.status = Period.PeriodStatus.REPORTED
                    period.reported_at = timezone.now()
                    period.save(update_fields=["status", "reported_at"])

        messages.success(request, f"Export skapad med {batch.row_count} rader.")
        return redirect("export:export_list")

    return render(
        request,
        "export/export_create.html",
        {
            "expenses": expense_qs,
            "mileage_reports": mileage_qs,
            "periods": periods_qs,
            "period_from": request.GET.get("period_from", ""),
            "period_to": request.GET.get("period_to", ""),
        },
    )


@admin_required
def export_list(request):
    batches = ExportBatch.objects.all()
    return render(request, "export/export_list.html", {"batches": batches})


@admin_required
def export_download(request, pk):
    batch = get_object_or_404(ExportBatch, pk=pk)
    if not batch.file:
        raise Http404
    return FileResponse(batch.file.open("rb"), as_attachment=True, filename=batch.file.name.split("/")[-1])
