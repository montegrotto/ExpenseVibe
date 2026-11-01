from django.conf import settings
from django.db import models
from django.utils import timezone


class ApprovalStatus(models.TextChoices):
    SUBMITTED = "submitted", "Inskickad"
    APPROVED = "approved", "Attesterad"
    REJECTED = "rejected", "Avvisad"
    EXPORTED = "exported", "Exporterad"


class Approvable(models.Model):
    """Delad statuslivscykel för Utlägg och Kilometerrapporter. Varje post
    attesteras för sig (inte grupperat i en periodrapport) och kan senare
    tas med i en Visma-export - se export.models.ExportBatch."""

    status = models.CharField(
        "Status", max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.SUBMITTED
    )
    submitted_at = models.DateTimeField("Inskickad", auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Beslutad av",
    )
    decided_at = models.DateTimeField("Beslutad", null=True, blank=True)
    decision_comment = models.CharField("Kommentar", max_length=500, blank=True)
    export_batch = models.ForeignKey(
        "export.ExportBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="Exportbatch",
    )
    exported_at = models.DateTimeField("Exporterad", null=True, blank=True)
    created_at = models.DateTimeField("Skapad", auto_now_add=True)
    updated_at = models.DateTimeField("Uppdaterad", auto_now=True)

    class Meta:
        abstract = True

    @classmethod
    def visible_to(cls, user):
        """Anställda ser bara sina egna poster; attestanter/admin ser allt
        (behövs för attesteringskön). Detta filtrerar listvyer - se resp.
        detaljvy för det strikta ägarskyddet mot IDOR."""
        if user.is_admin or user.is_approver:
            return cls.objects.all()
        return cls.objects.filter(employee=user)

    @classmethod
    def pending_for(cls, user):
        """Inskickade poster som `user` får besluta om - egna poster
        utesluts om självattestering är avstängd i inställningarna."""
        from absence.models import AbsenceSettings  # absence.models importerar core.models

        qs = cls.objects.filter(status=ApprovalStatus.SUBMITTED)
        if not AbsenceSettings.get_solo().allow_self_approval:
            qs = qs.exclude(employee=user)
        return qs

    @property
    def is_editable(self):
        return self.status in (ApprovalStatus.SUBMITTED, ApprovalStatus.REJECTED)

    @property
    def is_pending(self):
        return self.status == ApprovalStatus.SUBMITTED

    def approve(self, user):
        self.status = ApprovalStatus.APPROVED
        self.decided_by = user
        self.decided_at = timezone.now()
        self.decision_comment = ""
        self.save(update_fields=["status", "decided_by", "decided_at", "decision_comment", "updated_at"])

    def reject(self, user, reason):
        if not reason or not reason.strip():
            raise ValueError("En anledning måste anges vid avvisning.")
        self.status = ApprovalStatus.REJECTED
        self.decided_by = user
        self.decided_at = timezone.now()
        self.decision_comment = reason.strip()
        self.save(update_fields=["status", "decided_by", "decided_at", "decision_comment", "updated_at"])

    def resubmit(self):
        """Ägaren skickar in en avvisad post igen efter att ha rättat den.
        Full save (inte update_fields) - anroparna (expense_edit/
        mileagereport_edit) har just satt rättade fältvärden på instansen
        via form.save(commit=False), och de måste med till databasen."""
        self.status = ApprovalStatus.SUBMITTED
        self.decided_by = None
        self.decided_at = None
        self.decision_comment = ""
        self.save()

    def mark_exported(self, batch):
        self.status = ApprovalStatus.EXPORTED
        self.export_batch = batch
        self.exported_at = timezone.now()
        self.save(update_fields=["status", "export_batch", "exported_at", "updated_at"])
