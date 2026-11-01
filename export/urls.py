from django.urls import path

from export import views

app_name = "export"

urlpatterns = [
    path("ny/", views.export_create, name="export_create"),
    path("", views.export_list, name="export_list"),
    path("<int:pk>/hamta/", views.export_download, name="export_download"),
]
