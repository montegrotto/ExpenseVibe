"""JSON-API för iPhone-appen (ios/). Avsiktligt tunt: all validering och
affärslogik ligger kvar i de vanliga ModelForms/modellerna, vyerna här
översätter bara till/från JSON och ersätter sessions-/CSRF-skyddet med en
bärartoken (api.models.ApiToken) i Authorization-headern."""

import json
from functools import wraps

from django.contrib.auth import authenticate
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from absence.forms import AbsenceEntryForm
from absence.models import AbsenceEntry, AbsenceType, Period, TimeReport
from absence.services import submit_time_report
from absence.views import _parse_month, save_entry
from api.models import ApiToken
from attachments.forms import AttachmentUploadForm
from attachments.models import Attachment
from attachments.services import save_attachment_with_thumbnail
from attachments.views import _get_viewable_attachment
from core.views import _get_pending_item
from expenses.forms import ExpenseForm
from expenses.models import Category, Expense
from expenses.views import _initial_from_extraction
from mileage.forms import MileageReportForm
from mileage.models import MileageReport

_KINDS = {"utlagg": Expense, "kilometer": MileageReport, "tidrapport": TimeReport}


def _data(request):
    if request.content_type == "application/json":
        try:
            return json.loads(request.body or b"{}")
        except ValueError:
            return {}
    return request.POST


def _error(message, status):
    return JsonResponse({"error": message}, status=status)


def _form_errors(form):
    return JsonResponse({"errors": {field: [str(e) for e in errs] for field, errs in form.errors.items()}}, status=400)


def api_view(methods, approver=False):
    def decorator(view):
        @csrf_exempt
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return _error("Metoden stöds inte.", 405)
            header = request.headers.get("Authorization", "")
            token = None
            if header.startswith("Bearer "):
                token = ApiToken.objects.filter(key=header[7:]).select_related("user").first()
            now = timezone.now()
            if token is not None and token.last_used_at is None and now - token.created_at > ApiToken.QR_LIFETIME:
                token.delete()
                token = None
            if token is not None and (
                token.last_used_at is None or now - token.last_used_at > ApiToken.LAST_USED_RESOLUTION
            ):
                token.last_used_at = now
                token.save(update_fields=["last_used_at"])
            if token is None or not token.user.is_active:
                return _error("Inloggning krävs.", 401)
            if approver and not token.user.is_approver:
                return _error("Kräver attestantbehörighet.", 403)
            request.user = token.user
            request.api_token = token
            try:
                return view(request, *args, **kwargs)
            except Http404:
                return _error("Hittades inte.", 404)

        return wrapper

    return decorator


def _user_json(user):
    return {"id": user.pk, "name": str(user), "email": user.email, "is_approver": user.is_approver}


def _expense_json(expense):
    return {
        "id": expense.pk,
        "employee": str(expense.employee),
        "description": expense.description,
        "category": expense.category.name,
        "expense_date": expense.expense_date,
        "amount": expense.amount,
        "vat_amount": expense.vat_amount,
        "currency": expense.currency,
        "status": expense.status,
        "status_display": expense.get_status_display(),
        "decision_comment": expense.decision_comment,
        "attachment_id": expense.attachment_id,
    }


def _mileage_json(report):
    return {
        "id": report.pk,
        "employee": str(report.employee),
        "date": report.date,
        "start_location": report.start_location,
        "end_location": report.end_location,
        "purpose": report.purpose,
        "distance_km": report.distance_km,
        "rate_snapshot": report.rate_snapshot,
        "compensation_amount": report.compensation_amount,
        "status": report.status,
        "status_display": report.get_status_display(),
        "decision_comment": report.decision_comment,
    }


def _absence_entry_json(entry):
    return {
        "id": entry.pk,
        "date": entry.date,
        "absence_type": entry.absence_type.name,
        "whole_day": entry.absence_type.granularity == AbsenceType.Granularity.WHOLE_DAY,
        "hours": entry.effective_hours,
    }


def _time_report_json(report):
    return {
        "id": report.pk,
        "employee": str(report.employee),
        "period": str(report.period),
        "status": report.status,
        "status_display": report.get_status_display(),
        "decision_comment": report.decision_comment,
        "entries": [_absence_entry_json(e) for e in report.entries.order_by("date")],
    }


@csrf_exempt
def login(request):
    if request.method != "POST":
        return _error("Metoden stöds inte.", 405)
    data = _data(request)
    user = authenticate(request, username=data.get("email", ""), password=data.get("password", ""))
    if user is None:
        return _error("Fel e-postadress eller lösenord.", 401)
    if user.must_change_password:
        return _error("Du måste byta lösenord i webbappen innan appen kan användas.", 403)
    token = ApiToken.objects.create(
        user=user, name=str(data.get("device_name") or "")[:100], last_used_at=timezone.now()
    )
    return JsonResponse({"token": token.key, "user": _user_json(user)})


@api_view(["POST"])
def logout(request):
    request.api_token.delete()
    return JsonResponse({"ok": True})


@api_view(["GET"])
def me(request):
    return JsonResponse({"user": _user_json(request.user)})


@api_view(["GET"])
def categories(request):
    rows = Category.objects.filter(is_active=True).values("id", "name")
    return JsonResponse({"results": list(rows)})


@api_view(["POST"])
def attachment_upload(request):
    form = AttachmentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _form_errors(form)
    attachment = form.save(commit=False)
    attachment.uploaded_by = request.user
    save_attachment_with_thumbnail(attachment)
    return JsonResponse({"id": attachment.pk, "suggested": _initial_from_extraction(attachment)}, status=201)


@api_view(["GET"])
def attachment_file(request, pk):
    attachment = _get_viewable_attachment(request, pk)
    if not attachment.file:
        raise Http404
    return FileResponse(attachment.file.open("rb"), filename=attachment.file_name)


@api_view(["GET"])
def attachment_thumbnail(request, pk):
    attachment = _get_viewable_attachment(request, pk)
    if not attachment.thumbnail:
        raise Http404
    return FileResponse(attachment.thumbnail.open("rb"), filename=attachment.thumbnail_name)


@api_view(["GET", "POST"])
def expenses(request):
    if request.method == "GET":
        rows = Expense.objects.filter(employee=request.user).select_related("employee", "category")
        return JsonResponse({"results": [_expense_json(e) for e in rows]})
    data = _data(request)
    attachment_id = str(data.get("attachment_id", ""))
    if not attachment_id.isdigit():
        raise Http404
    attachment = get_object_or_404(
        Attachment, pk=attachment_id, uploaded_by=request.user, expense__isnull=True, deleted_at__isnull=True
    )
    form = ExpenseForm(data)
    if not form.is_valid():
        return _form_errors(form)
    expense = form.save(commit=False)
    expense.employee = request.user
    expense.attachment = attachment
    expense.save()
    return JsonResponse(_expense_json(expense), status=201)


@api_view(["GET", "POST"])
def mileage(request):
    if request.method == "GET":
        rows = MileageReport.objects.filter(employee=request.user).select_related("employee")
        return JsonResponse({"results": [_mileage_json(r) for r in rows]})
    form = MileageReportForm(_data(request))
    if not form.is_valid():
        return _form_errors(form)
    report = form.save(commit=False)
    report.employee = request.user
    report.recalculate_compensation()
    report.save()
    return JsonResponse(_mileage_json(report), status=201)


@api_view(["GET", "POST"])
def absence(request):
    """GET ?month=ÅÅÅÅ-MM: månadens frånvaro, som Frånvarokalendern i
    webben. POST: ny frånvaropost via samma formulär och sparlogik."""
    if request.method == "POST":
        form = AbsenceEntryForm(_data(request))
        entry = save_entry(form, request.user) if form.is_valid() else None
        if entry is None:
            return _form_errors(form)
        return JsonResponse(_absence_entry_json(entry), status=201)
    month = _parse_month(request.GET.get("month")) or timezone.localdate().replace(day=1)
    period = Period.objects.filter(month=month).first()
    report = TimeReport.objects.filter(employee=request.user, period=period).first() if period else None
    entries = (
        AbsenceEntry.objects.filter(employee=request.user, period=period).select_related("absence_type").order_by("date")
        if period
        else []
    )
    return JsonResponse(
        {
            "month": month.strftime("%Y-%m"),
            "period_open": bool(period and period.is_open),
            # Samma villkor gäller för att ändra poster och för att markera som färdig.
            "can_edit": bool(period and period.is_reportable_for(request.user)),
            "time_report": _time_report_json(report) if report else None,
            "entries": [_absence_entry_json(e) for e in entries],
            "types": list(AbsenceType.objects.filter(is_active=True).values("id", "name", "granularity")),
        }
    )


@api_view(["POST"])
def absence_delete(request, pk):
    entry = get_object_or_404(AbsenceEntry, pk=pk, employee=request.user)
    if not entry.period.is_reportable_for(request.user):
        return _error("Perioden är inte längre öppen för ändringar.", 409)
    entry.delete()
    return JsonResponse({"ok": True})


@api_view(["POST"])
def absence_submit(request):
    month = _parse_month(str(_data(request).get("month", "")))
    if month is None:
        return _error("Ogiltig månad.", 400)
    level, text = submit_time_report(request.user, month)
    if level == "error":
        return _error(text, 409)
    return JsonResponse({"message": text})


@api_view(["GET"], approver=True)
def approvals(request):
    pending_expenses = Expense.objects.filter(status="submitted").select_related("employee", "category")
    pending_mileage = MileageReport.objects.filter(status="submitted").select_related("employee")
    pending_time = TimeReport.objects.filter(status="submitted").select_related("employee", "period")
    return JsonResponse(
        {
            "expenses": [_expense_json(e) for e in pending_expenses.order_by("submitted_at")],
            "mileage": [_mileage_json(r) for r in pending_mileage.order_by("submitted_at")],
            "time_reports": [_time_report_json(r) for r in pending_time.order_by("submitted_at")],
        }
    )


def _pending(kind, pk):
    model = _KINDS.get(kind)
    if model is None:
        raise Http404
    item, error = _get_pending_item(model, pk)
    if item is None:
        return None, _error(error, 409)
    return item, None


@api_view(["POST"], approver=True)
def approve(request, kind, pk):
    item, error = _pending(kind, pk)
    if error:
        return error
    item.approve(request.user)
    return JsonResponse({"ok": True})


@api_view(["POST"], approver=True)
def reject(request, kind, pk):
    item, error = _pending(kind, pk)
    if error:
        return error
    try:
        item.reject(request.user, _data(request).get("reason", ""))
    except ValueError as exc:
        return _error(str(exc), 400)
    return JsonResponse({"ok": True})
