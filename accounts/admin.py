from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "employment_number", "is_approver", "is_admin", "is_active"]
    search_fields = ["email", "first_name", "last_name", "employment_number"]
    readonly_fields = ["date_joined"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personuppgifter", {"fields": ("first_name", "last_name", "employment_number", "personal_identity_number")}),
        ("Roller", {"fields": ("is_approver", "is_admin", "must_change_password")}),
        (
            "Behörigheter",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Viktiga datum", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "employment_number", "password1", "password2"),
            },
        ),
    )
