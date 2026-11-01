from django import forms
from PIL import Image

from attachments.models import Attachment


class AttachmentUploadForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.png,.jpg,.jpeg"}),
        }

    def clean_file(self):
        # FileExtensionValidator kollar bara filändelsen - en textfil döpt
        # till .jpg passerar den och kraschade tidigare först i
        # tumnagelgenereringen (efter att raden redan sparats). Verifiera
        # innehållet här istället, så användaren får ett formulärfel.
        file = self.cleaned_data["file"]
        if file.name.lower().endswith((".png", ".jpg", ".jpeg")):
            try:
                Image.open(file).verify()
            except Exception:
                raise forms.ValidationError("Filen går inte att läsa som en bild.")
            file.seek(0)
        return file
