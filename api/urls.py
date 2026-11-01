from django.urls import path

from api import views

app_name = "api"

urlpatterns = [
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("me/", views.me, name="me"),
    path("categories/", views.categories, name="categories"),
    path("attachments/", views.attachment_upload, name="attachment_upload"),
    path("attachments/<int:pk>/file/", views.attachment_file, name="attachment_file"),
    path("attachments/<int:pk>/thumbnail/", views.attachment_thumbnail, name="attachment_thumbnail"),
    path("expenses/", views.expenses, name="expenses"),
    path("mileage/", views.mileage, name="mileage"),
    path("absence/", views.absence, name="absence"),
    path("absence/<int:pk>/delete/", views.absence_delete, name="absence_delete"),
    path("absence/submit/", views.absence_submit, name="absence_submit"),
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/<str:kind>/<int:pk>/approve/", views.approve, name="approve"),
    path("approvals/<str:kind>/<int:pk>/reject/", views.reject, name="reject"),
]
