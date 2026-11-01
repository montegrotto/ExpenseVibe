from django import forms

from mileage.models import MileageRate, MileageReport


class MileageReportForm(forms.ModelForm):
    class Meta:
        model = MileageReport
        fields = ["date", "start_location", "end_location", "purpose", "distance_km"]
        widgets = {
            "date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "start_location": forms.TextInput(attrs={"class": "form-control"}),
            "end_location": forms.TextInput(attrs={"class": "form-control"}),
            "purpose": forms.TextInput(attrs={"class": "form-control"}),
            "distance_km": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        if date and MileageRate.current(on_date=date) is None:
            raise forms.ValidationError(
                "Ingen km-sats är konfigurerad för detta datum. Kontakta administratören."
            )
        return cleaned_data


class MileageRateForm(forms.ModelForm):
    class Meta:
        model = MileageRate
        fields = ["amount_per_km", "export_code", "export_code_name", "valid_from"]
        widgets = {
            "amount_per_km": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "export_code": forms.TextInput(attrs={"class": "form-control"}),
            "export_code_name": forms.TextInput(attrs={"class": "form-control"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }
