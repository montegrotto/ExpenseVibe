from django.contrib import admin

from mileage.models import MileageRate, MileageReport


@admin.register(MileageRate)
class MileageRateAdmin(admin.ModelAdmin):
    list_display = ["amount_per_km", "export_code", "valid_from"]


@admin.register(MileageReport)
class MileageReportAdmin(admin.ModelAdmin):
    list_display = ["employee", "date", "distance_km", "compensation_amount", "status"]
    list_filter = ["status"]
    search_fields = ["employee__email", "purpose"]
