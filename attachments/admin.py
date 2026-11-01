from django.contrib import admin

from attachments.models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["file_name", "uploaded_by", "uploaded_at", "deleted_at"]
    list_filter = ["deleted_at"]
    search_fields = ["file"]
