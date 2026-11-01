from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("attestering/", views.approval_queue, name="approval_queue"),
    path("attestering/<str:kind>/<int:pk>/godkann/", views.approve_item, name="approve_item"),
    path("attestering/<str:kind>/<int:pk>/avvisa/", views.reject_item, name="reject_item"),
]
