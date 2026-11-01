from django.urls import path

from attachments import views

app_name = "attachments"

urlpatterns = [
    path("ladda-upp/", views.upload, name="upload"),
    path("inkorg/", views.inbox, name="inbox"),
    path("<int:pk>/fil/", views.serve_file, name="file"),
    path("<int:pk>/miniatyr/", views.serve_thumbnail, name="thumbnail"),
    path("<int:pk>/ta-bort/", views.delete, name="delete"),
]
