from django.contrib import admin

from absence.models import AbsenceEntry, AbsenceSettings, AbsenceType, Period, TimeReport, WorkSchedule


@admin.register(AbsenceType)
class AbsenceTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "export_code", "granularity", "is_active"]


@admin.register(AbsenceSettings)
class AbsenceSettingsAdmin(admin.ModelAdmin):
    list_display = ["block_weekends_and_holidays", "updated_at", "updated_by"]


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = [
        "employee", "monday_hours", "tuesday_hours", "wednesday_hours", "thursday_hours", "friday_hours",
        "saturday_hours", "sunday_hours",
    ]
    search_fields = ["employee__email"]


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ["month", "status", "opened_at", "reported_at"]
    list_filter = ["status"]


@admin.register(TimeReport)
class TimeReportAdmin(admin.ModelAdmin):
    list_display = ["employee", "period", "status"]
    list_filter = ["status"]
    search_fields = ["employee__email"]


@admin.register(AbsenceEntry)
class AbsenceEntryAdmin(admin.ModelAdmin):
    list_display = ["employee", "date", "absence_type", "hours"]
    list_filter = ["absence_type"]
    search_fields = ["employee__email"]
