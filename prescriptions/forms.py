from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Prescription


MAX_PRESCRIPTION_FILE_SIZE = 5 * 1024 * 1024


class PrescriptionUploadForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = [
            "file",
            "doctor_name",
            "doctor_registration_number",
            "prescription_date",
            "notes",
        ]
        widgets = {
            "prescription_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file
        if file.size > MAX_PRESCRIPTION_FILE_SIZE:
            raise ValidationError("Prescription file must be 5 MB or smaller.")
        return file

    def clean_prescription_date(self):
        prescription_date = self.cleaned_data.get("prescription_date")
        if prescription_date and prescription_date > timezone.localdate():
            raise ValidationError("Prescription date cannot be in the future.")
        return prescription_date


class PrescriptionReviewForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ["status", "rejection_reason"]
        widgets = {
            "rejection_reason": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["status"].widget.attrs["class"] = "form-select"
