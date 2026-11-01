from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import Approvable


class Category(models.Model):
    """Adminstyrd kategori - admin lägger till/tar bort/byter namn utan
    kodändring. `code` motsvarar en löneart/utläggskod som redan är
    konfigurerad i Visma Lön 600 (se export/services.py) - ExpenseVibe
    definierar aldrig nya koder i Visma, bara refererar till befintliga."""

    name = models.CharField("Namn", max_length=100, unique=True)
    code = models.CharField("Kod (löneart)", max_length=10, blank=True)
    is_active = models.BooleanField("Aktiv", default=True)
    created_at = models.DateTimeField("Skapad", auto_now_add=True)
    updated_at = models.DateTimeField("Uppdaterad", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Kategori"
        verbose_name_plural = "Kategorier"

    def __str__(self):
        return self.name

    @property
    def can_delete(self):
        return not self.expenses.exists()


class Expense(Approvable):
    """Ett utlägg: en bilaga (kvitto/faktura) med kategori, belopp och
    datum. Attesteras för sig (inte i en periodrapport), se core.models.
    Approvable för statusflödet."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expenses", verbose_name="Anställd"
    )
    attachment = models.OneToOneField(
        "attachments.Attachment", on_delete=models.PROTECT, related_name="expense", verbose_name="Bilaga"
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="expenses", verbose_name="Kategori")
    description = models.CharField("Beskrivning", max_length=255)
    expense_date = models.DateField("Utläggsdatum")
    amount = models.DecimalField(
        "Belopp", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    vat_amount = models.DecimalField("Varav moms", max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField("Valuta", max_length=3, default="SEK")

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        verbose_name = "Utlägg"
        verbose_name_plural = "Utlägg"

    def __str__(self):
        return f"{self.description} ({self.amount} {self.currency})"
