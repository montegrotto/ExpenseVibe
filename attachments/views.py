from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from attachments.forms import AttachmentUploadForm
from attachments.models import Attachment
from attachments.services import save_attachment_with_thumbnail


@login_required
def upload(request):
    if request.method == "POST":
        form = AttachmentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.uploaded_by = request.user
            save_attachment_with_thumbnail(attachment)
            return redirect(f"{reverse('expenses:expense_create')}?attachment_id={attachment.pk}")
    else:
        form = AttachmentUploadForm()
    return render(request, "attachments/upload.html", {"form": form})


@login_required
def inbox(request):
    attachments = Attachment.objects.filter(
        expense__isnull=True, deleted_at__isnull=True, uploaded_by=request.user
    )
    return render(request, "attachments/inbox.html", {"attachments": attachments})


def _get_viewable_attachment(request, pk):
    """Bilagor (kvitton) är känsliga - bara uppladdaren själv samt
    attestanter/admin (som behöver se underlaget i attestkön) får hämta
    filinnehållet. Media serveras därför alltid via de här vyerna, aldrig
    direkt från /media/ (se expensevibe/urls.py och nginx/default.conf)."""
    attachment = get_object_or_404(Attachment, pk=pk)
    user = request.user
    if attachment.uploaded_by_id != user.pk and not (user.is_admin or user.is_approver):
        raise Http404
    return attachment


@login_required
def serve_file(request, pk):
    attachment = _get_viewable_attachment(request, pk)
    if not attachment.file:
        raise Http404
    return FileResponse(attachment.file.open("rb"), filename=attachment.file_name)


@login_required
def serve_thumbnail(request, pk):
    attachment = _get_viewable_attachment(request, pk)
    if not attachment.thumbnail:
        raise Http404
    return FileResponse(attachment.thumbnail.open("rb"), filename=attachment.thumbnail_name)


@login_required
def delete(request, pk):
    attachment = get_object_or_404(
        Attachment, pk=pk, uploaded_by=request.user, expense__isnull=True, deleted_at__isnull=True
    )
    if request.method == "POST":
        attachment.deleted_at = timezone.now()
        attachment.deleted_by = request.user
        attachment.delete_reason = request.POST.get("reason", "")
        attachment.save(update_fields=["deleted_at", "deleted_by", "delete_reason"])
        messages.success(request, "Bilagan är borttagen.")
        return redirect("attachments:inbox")
    return render(request, "attachments/delete_confirm.html", {"attachment": attachment})
