from django.urls import path

from expenses import views

app_name = "expenses"

urlpatterns = [
    path("nytt/", views.expense_create, name="expense_create"),
    path("", views.expense_list, name="expense_list"),
    path("<int:pk>/", views.expense_detail, name="expense_detail"),
    path("<int:pk>/redigera/", views.expense_edit, name="expense_edit"),
    path("<int:pk>/ta-bort/", views.expense_delete, name="expense_delete"),
    path("kategorier/", views.category_list, name="category_list"),
    path("kategorier/ny/", views.category_create, name="category_create"),
    path("kategorier/<int:pk>/", views.category_edit, name="category_edit"),
    path("kategorier/<int:pk>/ta-bort/", views.category_delete, name="category_delete"),
]
