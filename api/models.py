import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models


class ApiToken(models.Model):
    """Bärartoken för iPhone-appen (ios/). Skapas vid api:login, en per
    inloggning/enhet, och raderas när admin återställer användarens lösenord
    (accounts.views.user_set_password) så att en borttappad telefon kan
    stängas ute därifrån.

    En token som aldrig använts (last_used_at tomt - QR-koden i
    accounts.views.mobile_app) förfaller efter QR_LIFETIME, så att en visad
    men aldrig skannad kod inte blir en evig bakdörr."""

    QR_LIFETIME = timedelta(minutes=15)
    LAST_USED_RESOLUTION = timedelta(hours=1)

    key = models.CharField("Nyckel", max_length=64, unique=True, default=secrets.token_urlsafe)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField("Enhet", max_length=100, blank=True)
    created_at = models.DateTimeField("Skapad", auto_now_add=True)
    last_used_at = models.DateTimeField("Senast använd", null=True, blank=True)

    class Meta:
        verbose_name = "API-token"
        verbose_name_plural = "API-tokens"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ({self.created_at:%Y-%m-%d})"
