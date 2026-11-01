from django.urls import path

from mileage import views

app_name = "mileage"

urlpatterns = [
    path("nytt/", views.mileagereport_create, name="mileagereport_create"),
    path("", views.mileagereport_list, name="mileagereport_list"),
    path("<int:pk>/", views.mileagereport_detail, name="mileagereport_detail"),
    path("<int:pk>/redigera/", views.mileagereport_edit, name="mileagereport_edit"),
    path("<int:pk>/ta-bort/", views.mileagereport_delete, name="mileagereport_delete"),
    path("satser/", views.mileagerate_list, name="mileagerate_list"),
    path("satser/ny/", views.mileagerate_create, name="mileagerate_create"),
]
