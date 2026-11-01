from django.contrib import admin

from export.models import ExportBatch


@admin.register(ExportBatch)
class ExportBatchAdmin(admin.ModelAdmin):
    list_display = ["created_at", "created_by", "expense_count", "mileage_count", "total_amount"]
