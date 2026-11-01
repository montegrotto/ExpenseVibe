from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.decorators import admin_required
from mileage.forms import MileageRateForm, MileageReportForm
from mileage.models import MileageRate, MileageReport


@login_required
def mileagereport_create(request):
    if request.method == "POST":
        form = MileageReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.employee = request.user
            report.recalculate_compensation()
            report.save()
            messages.success(request, "Kilometerrapporten är inskickad för attestering.")
            return redirect("mileage:mileagereport_detail", pk=report.pk)
    else:
        form = MileageReportForm()
    return render(request, "mileage/mileagereport_form.html", {"form": form, "title": "Ny kilometerrapport"})


@login_required
def mileagereport_list(request):
    reports = MileageReport.visible_to(request.user).select_related("employee")
    return render(request, "mileage/mileagereport_list.html", {"reports": reports})


@login_required
def mileagereport_detail(request, pk):
    report = get_object_or_404(MileageReport.visible_to(request.user), pk=pk)
    return render(request, "mileage/mileagereport_detail.html", {"report": report})


@login_required
def mileagereport_edit(request, pk):
    report = get_object_or_404(MileageReport, pk=pk, employee=request.user)
    if not report.is_editable:
        messages.error(request, "Kilometerrapporten kan inte längre redigeras.")
        return redirect("mileage:mileagereport_detail", pk=report.pk)

    was_rejected = report.status == "rejected"
    if request.method == "POST":
        form = MileageReportForm(request.POST, instance=report)
        if form.is_valid():
            report = form.save(commit=False)
            report.recalculate_compensation()
            if was_rejected:
                report.resubmit()
            else:
                report.save()
            messages.success(request, "Kilometerrapporten är sparad.")
            return redirect("mileage:mileagereport_detail", pk=report.pk)
    else:
        form = MileageReportForm(instance=report)
    return render(
        request, "mileage/mileagereport_form.html", {"form": form, "report": report, "title": "Redigera kilometerrapport"}
    )


@login_required
def mileagereport_delete(request, pk):
    report = get_object_or_404(MileageReport, pk=pk, employee=request.user)
    if not report.is_editable:
        messages.error(request, "Kilometerrapporten kan inte längre tas bort.")
        return redirect("mileage:mileagereport_detail", pk=report.pk)
    if request.method == "POST":
        report.delete()
        messages.success(request, "Kilometerrapporten är borttagen.")
        return redirect("mileage:mileagereport_list")
    return render(request, "mileage/mileagereport_delete_confirm.html", {"report": report})


@admin_required
def mileagerate_list(request):
    rates = MileageRate.objects.all()
    return render(request, "mileage/mileagerate_list.html", {"rates": rates})


@admin_required
def mileagerate_create(request):
    if request.method == "POST":
        form = MileageRateForm(request.POST)
        if form.is_valid():
            rate = form.save(commit=False)
            rate.created_by = request.user
            rate.save()
            messages.success(request, "Km-satsen är sparad.")
            return redirect("mileage:mileagerate_list")
    else:
        form = MileageRateForm()
    return render(request, "mileage/mileagerate_form.html", {"form": form, "title": "Ny km-sats"})
