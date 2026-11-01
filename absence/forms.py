from django import forms
from django.db import models

from absence.models import AbsenceEntry, AbsenceSettings, AbsenceType, WorkSchedule


class AbsenceEntryForm(forms.ModelForm):
    class Meta:
        model = AbsenceEntry
        fields = ["date", "absence_type", "hours"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "absence_type": forms.Select(attrs={"class": "form-select"}),
            "hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Instansens nuvarande art måste vara valbar även om den
        # inaktiverats - annars kan en befintlig post aldrig mer sparas
        # (t.ex. vid rättning efter en avvisad tidrapport).
        types = AbsenceType.objects.filter(is_active=True)
        if self.instance.pk and self.instance.absence_type_id:
            types = AbsenceType.objects.filter(
                models.Q(is_active=True) | models.Q(pk=self.instance.absence_type_id)
            )
        self.fields["absence_type"].queryset = types
        self.fields["hours"].required = False
        self.fields["hours"].help_text = "Lämna tomt för frånvaroarter som alltid är en hel dag."


class AbsenceTypeForm(forms.ModelForm):
    class Meta:
        model = AbsenceType
        fields = ["name", "export_code", "granularity", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "export_code": forms.TextInput(attrs={"class": "form-control"}),
            "granularity": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class AbsenceSettingsForm(forms.ModelForm):
    class Meta:
        model = AbsenceSettings
        fields = ["block_weekends_and_holidays", "allow_self_approval"]
        widgets = {
            "block_weekends_and_holidays": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "allow_self_approval": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class WorkScheduleForm(forms.ModelForm):
    class Meta:
        model = WorkSchedule
        fields = [
            "monday_hours", "tuesday_hours", "wednesday_hours", "thursday_hours",
            "friday_hours", "saturday_hours", "sunday_hours",
        ]
        widgets = {
            field: forms.NumberInput(attrs={"class": "form-control", "step": "0.25"}) for field in fields
        }
