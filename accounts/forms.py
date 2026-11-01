from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from accounts.models import CustomUser


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="E-post", widget=forms.EmailInput(attrs={"autofocus": True, "class": "form-control"}))
    password = forms.CharField(label="Lösenord", widget=forms.PasswordInput(attrs={"class": "form-control"}))


class FirstAdminSignupForm(forms.ModelForm):
    """Bootstrap-formulär: bara nåbart så länge systemet inte har någon
    användare alls (se accounts/views.py::first_admin_signup). Ersätter ett
    tidigare CLI-kommando - den första personen som fyller i formuläret
    blir administratör direkt, ingen terminal krävs."""

    password = forms.CharField(label="Lösenord", widget=forms.PasswordInput(attrs={"class": "form-control"}), min_length=8)
    password_confirm = forms.CharField(
        label="Bekräfta lösenord", widget=forms.PasswordInput(attrs={"class": "form-control"}), min_length=8
    )

    class Meta:
        model = CustomUser
        fields = ["email", "first_name", "last_name", "employment_number"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "employment_number": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_password(self):
        password = self.cleaned_data["password"]
        password_validation.validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") and cleaned_data.get("password") != cleaned_data.get("password_confirm"):
            self.add_error("password_confirm", "Lösenorden matchar inte.")
        return cleaned_data

    def save(self, commit=True):
        user = CustomUser.objects.create_superuser(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            employment_number=self.cleaned_data["employment_number"],
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
        )
        # Till skillnad från UserCreateForm (där admin sätter ett lösenord
        # åt någon annan): den här personen valde lösenordet själv, så det
        # finns inget att tvinga fram ett byte av.
        user.must_change_password = False
        if commit:
            user.save(update_fields=["must_change_password"])
        return user


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(
        label="Lösenord",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        min_length=8,
        help_text="Användaren tvingas byta lösenord vid första inloggningen.",
    )

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "first_name",
            "last_name",
            "employment_number",
            "personal_identity_number",
            "is_approver",
            "is_admin",
        ]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "employment_number": forms.TextInput(attrs={"class": "form-control"}),
            "personal_identity_number": forms.TextInput(attrs={"class": "form-control"}),
            "is_approver": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_admin": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_password(self):
        password = self.cleaned_data["password"]
        password_validation.validate_password(password)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.must_change_password = True
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = [
            "email",
            "first_name",
            "last_name",
            "employment_number",
            "personal_identity_number",
            "is_approver",
            "is_admin",
            "is_active",
        ]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "employment_number": forms.TextInput(attrs={"class": "form-control"}),
            "personal_identity_number": forms.TextInput(attrs={"class": "form-control"}),
            "is_approver": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_admin": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        # Spärr mot total utlåsning: den sista aktiva administratören får
        # inte avadministreras eller inaktiveras - first_admin_signup är
        # permanent stängd så fort en användare finns, så det skulle inte
        # finnas någon väg tillbaka i appen.
        loses_admin = not cleaned_data.get("is_admin") or not cleaned_data.get("is_active")
        if self.instance.pk and self.instance.is_admin and self.instance.is_active and loses_admin:
            other_admins = CustomUser.objects.filter(is_admin=True, is_active=True).exclude(pk=self.instance.pk)
            if not other_admins.exists():
                raise forms.ValidationError(
                    "Det här är systemets enda aktiva administratör och kan inte "
                    "avadministreras eller inaktiveras."
                )
        return cleaned_data


class SetPasswordForm(forms.Form):
    password = forms.CharField(
        label="Nytt lösenord",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        min_length=8,
    )

    def clean_password(self):
        password = self.cleaned_data["password"]
        password_validation.validate_password(password)
        return password
