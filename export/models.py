from django.conf import settings
from django.db import models


class ExportBatch(models.Model):
    """En körd export till Visma Lön 600 (.tlu-fil). Attesterade utlägg och
    kilometerrapporter kopplas till batchen när de exporteras (se
    core.models.Approvable.export_batch), vilket både förhindrar
    dubbelexport och gör tidigare filer nedladdningsbara igen."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="export_batches",
        verbose_name="Skapad av",
    )
    created_at = models.DateTimeField("Skapad", auto_now_add=True)
    file = models.FileField("Exportfil (.tlu)", upload_to="exports/%Y/%m/", blank=True)
    period_from = models.DateField("Period från", null=True, blank=True)
    period_to = models.DateField("Period till", null=True, blank=True)
    expense_count = models.PositiveIntegerField("Antal utlägg", default=0)
    mileage_count = models.PositiveIntegerField("Antal kilometerrapporter", default=0)
    time_report_count = models.PositiveIntegerField("Antal tidrapporter", default=0)
    total_amount = models.DecimalField("Totalbelopp", max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Exportbatch"
        verbose_name_plural = "Exportbatcher"

    def __str__(self):
        return f"Export {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def row_count(self):
        return self.expense_count + self.mileage_count + self.time_report_count
