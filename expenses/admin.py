from django.contrib import admin

from expenses.models import Category, Expense


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active"]
    search_fields = ["name", "code"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["description", "employee", "category", "amount", "expense_date", "status"]
    list_filter = ["status", "category"]
    search_fields = ["description", "employee__email"]
