from django.urls import path

from absence import views

app_name = "absence"

urlpatterns = [
    path("", views.absence_calendar, name="absence_calendar"),
    path("post/ny/", views.absenceentry_create, name="absenceentry_create"),
    path("post/<int:pk>/redigera/", views.absenceentry_edit, name="absenceentry_edit"),
    path("post/<int:pk>/ta-bort/", views.absenceentry_delete, name="absenceentry_delete"),
    path("markera-fardig/", views.timereport_submit, name="timereport_submit"),
    path("tidrapporter/", views.timereport_list, name="timereport_list"),
    path("tidrapporter/<int:pk>/", views.timereport_detail, name="timereport_detail"),
    path("franvaroarter/", views.absencetype_list, name="absencetype_list"),
    path("franvaroarter/ny/", views.absencetype_create, name="absencetype_create"),
    path("franvaroarter/<int:pk>/redigera/", views.absencetype_edit, name="absencetype_edit"),
    path("franvaroarter/<int:pk>/ta-bort/", views.absencetype_delete, name="absencetype_delete"),
    path("perioder/", views.period_list, name="period_list"),
    path("perioder/oppna/", views.period_open, name="period_open"),
    path("perioder/<int:pk>/ateroppna/", views.period_reopen, name="period_reopen"),
    path("installningar/", views.absencesettings_edit, name="absencesettings_edit"),
    path("arbetsscheman/", views.workschedule_list, name="workschedule_list"),
    path("arbetsscheman/<int:pk>/", views.workschedule_edit, name="workschedule_edit"),
]
