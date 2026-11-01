from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("konto/", include("accounts.urls", namespace="accounts")),
    path("bilagor/", include("attachments.urls", namespace="attachments")),
    path("utlagg/", include("expenses.urls", namespace="expenses")),
    path("kilometer/", include("mileage.urls", namespace="mileage")),
    path("franvaro/", include("absence.urls", namespace="absence")),
    path("export/", include("export.urls", namespace="export")),
    path("api/", include("api.urls", namespace="api")),
    path("", include("core.urls", namespace="core")),
]

# Ingen rå /media/-servering ens i DEBUG - bilagor (kvitton) innehåller
# känsliga uppgifter och serveras uteslutande via de behörighetsskyddade
# vyerna i attachments (attachments:file/attachments:thumbnail) respektive
# export:export_download.
