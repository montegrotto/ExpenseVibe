import calendar
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum

from absence.holidays import is_non_working_day
from core.models import Approvable, ApprovalStatus


class AbsenceType(models.Model):
    """Adminstyrd frånvaroart - motsvarar expenses.Category men för
    tidrapportering. `export_code` är Visma Lön 600s TimeCode (se
    export/services.py <Time>-element), en annan kod-rymd än
    Category.code/MileageRate.export_code som är OutlayCode."""

    class Granularity(models.TextChoices):
        HOURS = "hours", "Timmar"
        WHOLE_DAY = "whole_day", "Hel dag"

    name = models.CharField("Namn", max_length=100, unique=True)
    export_code = models.CharField("Kod (tidkod)", max_length=10, blank=True)
    granularity = models.CharField("Granularitet", max_length=10, choices=Granularity.choices)
    is_active = models.BooleanField("Aktiv", default=True)
    created_at = models.DateTimeField("Skapad", auto_now_add=True)
    updated_at = models.DateTimeField("Uppdaterad", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Frånvaroart"
        verbose_name_plural = "Frånvaroarter"

    def __str__(self):
        return self.name

    @property
    def can_delete(self):
        return not self.entries.exists()


class AbsenceSettings(models.Model):
    """Enda-rad-konfiguration (singleton, pk alltid 1)."""

    block_weekends_and_holidays = models.BooleanField(
        "Blockera rapportering på lördagar, söndagar och helgdagar", default=True
    )
    updated_at = models.DateTimeField("Uppdaterad", auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Uppdaterad av",
    )

    class Meta:
        verbose_name = "Frånvaroinställning"
        verbose_name_plural = "Frånvaroinställningar"

    def __str__(self):
        return "Frånvaroinställningar"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def blocks_date(self, check_date):
        """Om `check_date` är avstängd för rapportering enligt den här
        inställningen - lördag/söndag, en svensk helgdag, eller en sådan
        afton/klämdag (julafton, nyårsafton, midsommarafton) som räknas
        som arbetsfri, se absence.holidays.is_non_working_day. Alltid
        False om inställningen är avstängd."""
        if not self.block_weekends_and_holidays:
            return False
        saturday = 5
        return check_date.weekday() >= saturday or is_non_working_day(check_date)


class WorkSchedule(models.Model):
    """Per-anställd veckoschema - timmar per veckodag. Styr både
    NormalWorkingTime-blocket i Visma-exporten (export/services.py -
    Visma kräver en rad per kalenderdag i den anställdes period, matchad
    mot schemat som redan är konfigurerat på personen i Lön) och
    omräkningen av Hel dag-frånvaro till timmar (se
    AbsenceEntry.workday_hours_snapshot) - en anställds "en hel dag" är
    helt enkelt deras schemalagda timmar just den veckodagen, vilket
    automatiskt blir rätt även för deltidare med ojämn vecka.

    Medvetet INTE versionerad - AbsenceEntry snapshotar värdet vid
    skapandet (workday_hours_snapshot), så historiken är trygg även om
    admin justerar schemat senare (t.ex. vid ändrad sysselsättningsgrad)."""

    employee = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="work_schedule", verbose_name="Anställd"
    )
    _hours_validators = [MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("24.00"))]
    monday_hours = models.DecimalField(
        "Måndag", max_digits=4, decimal_places=2, default=Decimal("8.00"), validators=_hours_validators
    )
    tuesday_hours = models.DecimalField(
        "Tisdag", max_digits=4, decimal_places=2, default=Decimal("8.00"), validators=_hours_validators
    )
    wednesday_hours = models.DecimalField(
        "Onsdag", max_digits=4, decimal_places=2, default=Decimal("8.00"), validators=_hours_validators
    )
    thursday_hours = models.DecimalField(
        "Torsdag", max_digits=4, decimal_places=2, default=Decimal("8.00"), validators=_hours_validators
    )
    friday_hours = models.DecimalField(
        "Fredag", max_digits=4, decimal_places=2, default=Decimal("8.00"), validators=_hours_validators
    )
    saturday_hours = models.DecimalField(
        "Lördag", max_digits=4, decimal_places=2, default=Decimal("0.00"), validators=_hours_validators
    )
    sunday_hours = models.DecimalField(
        "Söndag", max_digits=4, decimal_places=2, default=Decimal("0.00"), validators=_hours_validators
    )
    updated_at = models.DateTimeField("Uppdaterad", auto_now=True)

    class Meta:
        verbose_name = "Arbetsschema"
        verbose_name_plural = "Arbetsscheman"

    def __str__(self):
        return f"Arbetsschema – {self.employee}"

    _HOURS_FIELDS_BY_WEEKDAY = (
        "monday_hours", "tuesday_hours", "wednesday_hours", "thursday_hours",
        "friday_hours", "saturday_hours", "sunday_hours",
    )

    def hours_for_weekday(self, weekday):
        """`weekday`: 0=måndag ... 6=söndag, som date.weekday()."""
        return getattr(self, self._HOURS_FIELDS_BY_WEEKDAY[weekday])

    def hours_for_date(self, check_date):
        return self.hours_for_weekday(check_date.weekday())

    @classmethod
    def get_for_employee(cls, employee):
        obj, _ = cls.objects.get_or_create(employee=employee)
        return obj


class Period(models.Model):
    """Redovisningsperiod för frånvaro - alltid en hel kalendermånad.
    Avsaknad av en Period-rad för en månad betyder implicit stängt, samma
    "ingen rad = spärrat"-idé som redan gäller attestering på andra håll
    i systemet."""

    class PeriodStatus(models.TextChoices):
        OPEN = "open", "Öppen"
        REPORTED = "reported", "Rapporterad"

    month = models.DateField("Månad", unique=True)
    status = models.CharField("Status", max_length=10, choices=PeriodStatus.choices, default=PeriodStatus.OPEN)
    opened_at = models.DateTimeField("Öppnad", auto_now_add=True)
    reported_at = models.DateTimeField("Rapporterad", null=True, blank=True)

    class Meta:
        ordering = ["-month"]
        verbose_name = "Period"
        verbose_name_plural = "Perioder"

    def __str__(self):
        return self.month.strftime("%Y-%m")

    def save(self, *args, **kwargs):
        self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)

    @property
    def month_end(self):
        last_day = calendar.monthrange(self.month.year, self.month.month)[1]
        return self.month.replace(day=last_day)

    @property
    def is_open(self):
        return self.status == self.PeriodStatus.OPEN

    def is_reportable_for(self, employee):
        """Om `employee` just nu får skapa/ändra/ta bort AbsenceEntry-rader
        för den här perioden. Snävare än Approvable.is_editable (som också
        skulle inkludera SUBMITTED) - se TimeReport-docstringen för varför."""
        if not self.is_open:
            return False
        report = TimeReport.objects.filter(employee=employee, period=self).first()
        return report is None or report.status == ApprovalStatus.REJECTED


class TimeReport(Approvable):
    """En anställds tidrapport för en period. Ärver core.models.Approvable
    helt oförändrad, precis som Expense/MileageReport.

    Design-nyckel: att skapa TimeReport-raden ÄR inlämningen ("Markera som
    färdig"), precis som att skapa ett Expense redan idag innebär att det
    är inskickat (status defaultar till SUBMITTED). Innan dess finns ingen
    TimeReport-rad - AbsenceEntry är fristående och fylls i fritt under
    månaden. Detta undviker att core.models.Approvable (som Expense/
    MileageReport redan beror på oförändrad) behöver ett nytt
    utkast-tillstånd.

    AbsenceEntry-rader tillåts INTE redigeras medan status är SUBMITTED
    (till skillnad från Expense/MileageReports is_editable, som medvetet
    inkluderar SUBMITTED) - se Period.is_reportable_for. Annars skulle en
    anställd kunna lägga till/ta bort dagar efter att en attestant redan
    öppnat tidrapporten för granskning men innan de hunnit attestera, utan
    att attestanten notifieras om att underlaget ändrats."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="time_reports", verbose_name="Anställd"
    )
    period = models.ForeignKey(Period, on_delete=models.PROTECT, related_name="time_reports", verbose_name="Period")

    class Meta:
        ordering = ["-period__month"]
        verbose_name = "Tidrapport"
        verbose_name_plural = "Tidrapporter"
        constraints = [
            models.UniqueConstraint(fields=["employee", "period"], name="unique_timereport_per_employee_period")
        ]

    def __str__(self):
        return f"{self.employee} – {self.period}"

    @property
    def entries(self):
        return AbsenceEntry.objects.filter(employee=self.employee, period=self.period).select_related(
            "absence_type"
        )


class AbsenceEntry(models.Model):
    """En frånvaropost: ett datum + en frånvaroart. Flera poster får finnas
    samma datum för samma anställd (t.ex. delad sjuk/vård av barn), så
    länge de inte är av typen Hel dag (som är exklusiv för sitt datum) och
    summan av timmar inte överstiger personens schemalagda timmar den
    veckodagen (se WorkSchedule).

    Fristående från TimeReport (ingen FK däremellan) - kan fyllas i fritt
    under hela månaden innan tidrapporten någonsin skapas/skickas in, se
    TimeReport. `period` hålls som egen FK (denormaliserat) för enkla
    queries i kalendern och exporten, samma avvägning som
    MileageReport.mileage_rate behålls som FK istället för att härledas
    rent ur datum."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="absence_entries", verbose_name="Anställd"
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name="absence_entries", verbose_name="Period"
    )
    date = models.DateField("Datum")
    absence_type = models.ForeignKey(
        AbsenceType, on_delete=models.PROTECT, related_name="entries", verbose_name="Frånvaroart"
    )
    hours = models.DecimalField(
        "Timmar", max_digits=4, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # Snapshot av WorkSchedule.hours_for_date(date) vid skapandet - bara
    # satt för Hel dag-poster (se AbsenceType.Granularity.WHOLE_DAY).
    # Skyddar redan inlämnade poster mot att tyst ändra värde om admin
    # justerar personens schema senare, samma idé som
    # MileageReport.rate_snapshot.
    workday_hours_snapshot = models.DecimalField(
        "Timmar vid inlämning (hel dag)", max_digits=4, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField("Skapad", auto_now_add=True)
    updated_at = models.DateTimeField("Uppdaterad", auto_now=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Frånvaropost"
        verbose_name_plural = "Frånvaroposter"

    def __str__(self):
        return f"{self.date} – {self.absence_type}"

    @property
    def effective_hours(self):
        if self.absence_type.granularity == AbsenceType.Granularity.WHOLE_DAY:
            return self.workday_hours_snapshot
        return self.hours

    def clean(self):
        super().clean()
        errors = {}

        if self.absence_type_id:
            is_whole_day = self.absence_type.granularity == AbsenceType.Granularity.WHOLE_DAY
            if is_whole_day and self.hours is not None:
                errors["hours"] = "Hel dag-frånvaro anges inte i timmar."
            elif not is_whole_day and self.hours is None:
                errors["hours"] = "Ange antal timmar för denna frånvaroart."
            if not self.pk and not self.absence_type.is_active:
                errors["absence_type"] = "Frånvaroarten är inaktiverad och kan inte längre användas."

        if self.period_id and self.date:
            if not (self.period.month <= self.date <= self.period.month_end):
                errors.setdefault("date", "Datumet måste ligga inom perioden.")
            elif AbsenceSettings.get_solo().blocks_date(self.date):
                errors.setdefault("date", "Frånvaro kan inte rapporteras på lördagar, söndagar eller helgdagar.")

        if self.employee_id and self.period_id:
            if not self.period.is_reportable_for(self.employee):
                report = TimeReport.objects.filter(employee=self.employee, period=self.period).first()
                if report is not None:
                    errors["__all__"] = (
                        f"Tidrapporten är {report.get_status_display().lower()} och kan inte längre ändras."
                    )
                else:
                    errors["__all__"] = "Perioden är inte öppen för rapportering."

        if self.employee_id and self.date and self.absence_type_id and "hours" not in errors:
            same_day = AbsenceEntry.objects.filter(employee_id=self.employee_id, date=self.date)
            if self.pk:
                same_day = same_day.exclude(pk=self.pk)
            is_whole_day = self.absence_type.granularity == AbsenceType.Granularity.WHOLE_DAY
            if is_whole_day and same_day.exists():
                errors["absence_type"] = "En hel dag kan inte kombineras med andra frånvaroposter samma datum."
            elif not is_whole_day and same_day.filter(
                absence_type__granularity=AbsenceType.Granularity.WHOLE_DAY
            ).exists():
                errors["absence_type"] = "Datumet har redan en hel dag-post."
            elif not is_whole_day:
                daily_cap = WorkSchedule.get_for_employee(self.employee).hours_for_date(self.date)
                hours_sum = same_day.filter(absence_type__granularity=AbsenceType.Granularity.HOURS).aggregate(
                    total=Sum("hours")
                )["total"] or Decimal("0")
                if hours_sum + (self.hours or Decimal("0")) > daily_cap:
                    errors["hours"] = (
                        f"Summan av timmar för dagen får inte överstiga {daily_cap} (schemalagd arbetstid)."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.absence_type.granularity == AbsenceType.Granularity.WHOLE_DAY:
            # Räknas om vid VARJE save, inte bara första - posten kan bara
            # sparas medan perioden är redigerbar (se clean/is_reportable_for),
            # och flyttas den till en annan veckodag måste snapshotten följa
            # det nya datumets schemalagda timmar. Inlämnade poster sparas
            # aldrig om, så skyddet mot senare admin-schemaändringar består.
            self.workday_hours_snapshot = WorkSchedule.get_for_employee(self.employee).hours_for_date(self.date)
        else:
            self.workday_hours_snapshot = None
        super().save(*args, **kwargs)
