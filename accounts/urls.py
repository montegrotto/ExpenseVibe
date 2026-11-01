from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("logga-in/", views.EmailLoginView.as_view(), name="login"),
    path("logga-ut/", LogoutView.as_view(), name="logout"),
    path("skapa-forsta-kontot/", views.first_admin_signup, name="first_admin_signup"),
    path("byt-losenord/", views.ForcedPasswordChangeView.as_view(), name="password_change"),
    path("byt-losenord/klart/", views.password_change_done, name="password_change_done"),
    path("mobilappen/", views.mobile_app, name="mobile_app"),
    path("anvandare/", views.user_list, name="user_list"),
    path("anvandare/ny/", views.user_create, name="user_create"),
    path("anvandare/<int:pk>/", views.user_edit, name="user_edit"),
    path("anvandare/<int:pk>/losenord/", views.user_set_password, name="user_set_password"),
]
