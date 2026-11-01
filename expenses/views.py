from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from attachments.models import Attachment
from core.decorators import admin_required
from expenses.forms import CategoryForm, ExpenseForm
from expenses.models import Category, Expense


def _initial_from_extraction(attachment):
    """Förifyller bara som förslag - aldrig auktoritativt, se avsnitt 4 i
    planen. Ogiltiga/orimliga värden ignoreras tyst, användaren fyller i
    resten själv."""
    initial = {}
    data = attachment.extracted_data or {}

    if data.get("datum"):
        initial["expense_date"] = data["datum"]

    if data.get("totalbelopp"):
        try:
            initial["amount"] = Decimal(str(data["totalbelopp"]))
        except (InvalidOperation, TypeError):
            pass

    if data.get("momsbelopp"):
        try:
            initial["vat_amount"] = Decimal(str(data["momsbelopp"]))
        except (InvalidOperation, TypeError):
            pass

    if data.get("valuta"):
        initial["currency"] = data["valuta"]

    return initial


@login_required
def expense_create(request):
    attachment_id = request.GET.get("attachment_id") or request.POST.get("attachment_id")
    # Enda stället där ett pk kommer från query-/POST-parametrar istället
    # för <int:pk>-URL-convertern - icke-numeriskt värde ska ge 404, inte
    # ValueError/500 inne i get_object_or_404.
    if not str(attachment_id or "").isdigit():
        raise Http404
    attachment = get_object_or_404(
        Attachment, pk=attachment_id, uploaded_by=request.user, expense__isnull=True, deleted_at__isnull=True
    )

    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.employee = request.user
            expense.attachment = attachment
            expense.save()
            messages.success(request, "Utlägget är inskickat för attestering.")
            return redirect("expenses:expense_detail", pk=expense.pk)
    else:
        form = ExpenseForm(initial=_initial_from_extraction(attachment))

    extracted = attachment.extracted_data or {}
    return render(
        request,
        "expenses/expense_form.html",
        {
            "form": form,
            "attachment": attachment,
            "extracted": extracted,
            "needs_review": extracted.get("behöver_granskning", False) or not extracted,
            "title": "Nytt utlägg",
        },
    )


@login_required
def expense_list(request):
    expenses = Expense.visible_to(request.user).select_related("employee", "category", "attachment")
    return render(request, "expenses/expense_list.html", {"expenses": expenses})


@login_required
def expense_detail(request, pk):
    expense = get_object_or_404(Expense.visible_to(request.user), pk=pk)
    return render(request, "expenses/expense_detail.html", {"expense": expense})


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk, employee=request.user)
    if not expense.is_editable:
        messages.error(request, "Utlägget kan inte längre redigeras.")
        return redirect("expenses:expense_detail", pk=expense.pk)

    was_rejected = expense.status == "rejected"
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            expense = form.save(commit=False)
            if was_rejected:
                expense.resubmit()
            else:
                expense.save()
            messages.success(request, "Utlägget är sparat.")
            return redirect("expenses:expense_detail", pk=expense.pk)
    else:
        form = ExpenseForm(instance=expense)
    return render(
        request,
        "expenses/expense_form.html",
        {"form": form, "expense": expense, "attachment": expense.attachment, "title": "Redigera utlägg"},
    )


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, employee=request.user)
    if not expense.is_editable:
        messages.error(request, "Utlägget kan inte längre tas bort.")
        return redirect("expenses:expense_detail", pk=expense.pk)
    if request.method == "POST":
        expense.delete()
        messages.success(request, "Utlägget är borttaget.")
        return redirect("expenses:expense_list")
    return render(request, "expenses/expense_delete_confirm.html", {"expense": expense})


@admin_required
def category_list(request):
    categories = Category.objects.all()
    return render(request, "expenses/category_list.html", {"categories": categories})


@admin_required
def category_create(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Kategorin är skapad.")
            return redirect("expenses:category_list")
    else:
        form = CategoryForm()
    return render(request, "expenses/category_form.html", {"form": form, "title": "Ny kategori"})


@admin_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Kategorin är uppdaterad.")
            return redirect("expenses:category_list")
    else:
        form = CategoryForm(instance=category)
    return render(request, "expenses/category_form.html", {"form": form, "title": f"Redigera {category.name}"})


@admin_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        if category.can_delete:
            category.delete()
            messages.success(request, "Kategorin är borttagen.")
        else:
            category.is_active = False
            category.save(update_fields=["is_active"])
            messages.info(request, "Kategorin har kopplade utlägg och kunde inte tas bort - den är inaktiverad istället.")
        return redirect("expenses:category_list")
    return render(request, "expenses/category_delete_confirm.html", {"category": category})
