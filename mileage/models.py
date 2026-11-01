from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import Approvable


class MileageRate(models.Model):
    """Versionerad km-sats - en ny rad läggs till varje gång Skatteverkets
    schablonbelopp ändras, istället för att ett befintligt värde redigeras
    i plats. Det gör att gamla kilometerrapporter behåller den sats de
    faktiskt beräknades med, se MileageReport.rate_snapshot."""

    amount_per_km = models.DecimalField(
        "Kr/km", max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    export_code = models.CharField("Kod (löneart)", max_length=10, blank=True)
    export_code_name = models.CharField("Benämning", max_length=50, blank=True, default="Bilersättning (km)")
    valid_from = models.DateField("Gäller från")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField("Skapad", auto_now_add=True)

    class Meta:
        ordering = ["-valid_from"]
        verbose_name = "Km-sats"
        verbose_name_plural = "Km-satser"

    def __str__(self):
        return f"{self.amount_per_km} kr/km fr.o.m. {self.valid_from}"

    @classmethod
    def current(cls, on_date):
        # "-pk" som tie-break: läggs två satser in med samma valid_from
        # (admin rättar en felinmatning) ska den senast skapade vinna,
        # inte databasens fysiska radordning.
        return cls.objects.filter(valid_from__lte=on_date).order_by("-valid_from", "-pk").first()


class MileageReport(Approvable):
    """En kilometerrapport: datum, från/till, syfte och antal körda
    kilometer. Ersättningen räknas ut automatiskt utifrån den km-sats som
    gällde vid resans datum (inte inlämningsdatumet)."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mileage_reports", verbose_name="Anställd"
    )
    date = models.DateField("Datum")
    start_location = models.CharField("Från", max_length=200)
    end_location = models.CharField("Till", max_length=200)
    purpose = models.CharField("Syfte", max_length=255)
    distance_km = models.DecimalField(
        "Antal km", max_digits=6, decimal_places=1, validators=[MinValueValidator(Decimal("0.1"))]
    )
    # FK till hela raden (inte bara en kopierad summa) så att OutlayCode/
    # OutlayCodeName för Visma-exporten (export/services.py) alltid går att
    # slå upp historiskt korrekt, även om en senare tillagd MileageRate-rad
    # har en annan kod. PROTECT: en km-sats som redan är använd i en
    # inlämnad rapport får inte tas bort.
    mileage_rate = models.ForeignKey(
        MileageRate, on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="Använd km-sats"
    )
    rate_snapshot = models.DecimalField("Sats vid inlämning (kr/km)", max_digits=6, decimal_places=2)
    compensation_amount = models.DecimalField("Ersättningsbelopp", max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Kilometerrapport"
        verbose_name_plural = "Kilometerrapporter"

    def __str__(self):
        return f"{self.start_location} → {self.end_location} ({self.distance_km} km)"

    def recalculate_compensation(self):
        rate = MileageRate.current(on_date=self.date)
        if rate is None:
            return False
        # distance_km kan vara en sträng/float här om posten byggts utanför
        # ett ModelForm (t.ex. i ett skal eller en framtida batchoperation) -
        # ModelForm.cleaned_data ger redan Decimal, men det ska inte krävas.
        distance = Decimal(str(self.distance_km))
        self.mileage_rate = rate
        self.rate_snapshot = rate.amount_per_km
        self.compensation_amount = (distance * rate.amount_per_km).quantize(Decimal("0.01"))
        return True
