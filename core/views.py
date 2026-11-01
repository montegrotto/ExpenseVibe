from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from absence.models import TimeReport
from core.decorators import approver_required
from expenses.models import Expense
from mileage.models import MileageReport

_MODELS_BY_KIND = {"utlagg": Expense, "kilometer": MileageReport, "tidrapport": TimeReport}


@login_required
def dashboard(request):
    user = request.user
    my_expenses = Expense.objects.filter(employee=user)
    my_mileage = MileageReport.objects.filter(employee=user)
    my_time_reports = TimeReport.objects.filter(employee=user)
    context = {
        "my_expense_counts": {
            "submitted": my_expenses.filter(status="submitted").count(),
            "approved": my_expenses.filter(status="approved").count(),
            "rejected": my_expenses.filter(status="rejected").count(),
        },
        "my_mileage_counts": {
            "submitted": my_mileage.filter(status="submitted").count(),
            "approved": my_mileage.filter(status="approved").count(),
            "rejected": my_mileage.filter(status="rejected").count(),
        },
        "my_time_report_counts": {
            "submitted": my_time_reports.filter(status="submitted").count(),
            "approved": my_time_reports.filter(status="approved").count(),
            "rejected": my_time_reports.filter(status="rejected").count(),
        },
        "recent_expenses": my_expenses.order_by("-created_at")[:5],
        "recent_mileage": my_mileage.order_by("-created_at")[:5],
        "recent_time_reports": my_time_reports.select_related("period").order_by("-created_at")[:5],
    }
    if user.is_approver:
        context["approval_queue_count"] = (
            Expense.objects.filter(status="submitted").count()
            + MileageReport.objects.filter(status="submitted").count()
            + TimeReport.objects.filter(status="submitted").count()
        )
    return render(request, "core/dashboard.html", context)


@approver_required
def approval_queue(request):
    expenses = Expense.objects.filter(status="submitted").select_related("employee", "category").order_by(
        "submitted_at"
    )
    mileage_reports = MileageReport.objects.filter(status="submitted").select_related("employee").order_by(
        "submitted_at"
    )
    time_reports = TimeReport.objects.filter(status="submitted").select_related("employee", "period").order_by(
        "submitted_at"
    )
    return render(
        request,
        "core/approval_queue.html",
        {"expenses": expenses, "mileage_reports": mileage_reports, "time_reports": time_reports},
    )


def _get_pending_item(model, pk):
    """Hämtar posten om den fortfarande går att besluta om. Returnerar
    (item, felmeddelande) - vid fel är item None. Ett redan fattat beslut
    (dubbelklick/kapplöpning) ska ge ett meddelande i kön, inte en rå 404.
    Ingen jävsspärr - självattestering är ett uttryckligt beslut i planen,
    se expenses.tests.test_self_attestation_is_allowed."""
    item = get_object_or_404(model, pk=pk)
    if not item.is_pending:
        return None, "Posten är redan beslutad."
    return item, None


@approver_required
def approve_item(request, kind, pk):
    model = _MODELS_BY_KIND.get(kind)
    if model is None or request.method != "POST":
        return redirect("core:approval_queue")
    item, error = _get_pending_item(model, pk)
    if item is None:
        messages.error(request, error)
        return redirect("core:approval_queue")
    item.approve(request.user)
    messages.success(request, "Posten är attesterad.")
    return redirect("core:approval_queue")


@approver_required
def reject_item(request, kind, pk):
    model = _MODELS_BY_KIND.get(kind)
    if model is None:
        return redirect("core:approval_queue")
    item, error = _get_pending_item(model, pk)
    if item is None:
        messages.error(request, error)
        return redirect("core:approval_queue")
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            item.reject(request.user, reason)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("core:approval_queue")
        messages.success(request, "Posten är avvisad.")
        return redirect("core:approval_queue")
    return render(request, "core/reject_confirm.html", {"item": item, "kind": kind})
