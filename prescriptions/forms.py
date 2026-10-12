from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import Prescription, PrescriptionItem


MAX_PRESCRIPTION_FILE_SIZE = 5 * 1024 * 1024


class PrescriptionUploadForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = [
            "patient_name",
            "patient_date_of_birth",
            "patient_gender",
            "file",
            "doctor_name",
            "doctor_registration_number",
            "clinic_name",
            "clinic_contact",
            "prescription_date",
            "requested_medicines",
            "notes",
            "customer_consent",
        ]
        widgets = {
            "patient_date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "prescription_date": forms.DateInput(attrs={"type": "date"}),
            "requested_medicines": forms.Textarea(
                attrs={"rows": 4, "placeholder": "One medicine or requested item per line"}
            ),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "customer_consent": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient_name"].required = True
        self.fields["customer_consent"].required = True
        for name, field in self.fields.items():
            if name == "customer_consent":
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        self.fields["customer_consent"].label = (
            "I confirm this prescription belongs to me or a person I am authorised to act for, "
            "and I consent to secure pharmacy review."
        )

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

    def clean_patient_date_of_birth(self):
        date_of_birth = self.cleaned_data.get("patient_date_of_birth")
        if date_of_birth and date_of_birth > timezone.localdate():
            raise ValidationError("Date of birth cannot be in the future.")
        return date_of_birth

    def clean_customer_consent(self):
        consent = self.cleaned_data.get("customer_consent")
        if not consent:
            raise ValidationError("Consent is required before the prescription can be reviewed.")
        return consent


class PrescriptionReviewForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = [
            "status",
            "valid_until",
            "max_fulfillments",
            "original_required_on_delivery",
            "clarification_message",
            "rejection_reason",
            "review_notes",
            "prescriber_verified",
            "patient_identity_verified",
            "clinical_validation_status",
            "validation_flags",
            "alteration_notes",
        ]
        widgets = {
            "valid_until": forms.DateInput(attrs={"type": "date"}),
            "clarification_message": forms.Textarea(attrs={"rows": 3}),
            "rejection_reason": forms.Textarea(attrs={"rows": 3}),
            "review_notes": forms.Textarea(attrs={"rows": 4}),
            "validation_flags": forms.Textarea(attrs={"rows": 3, "placeholder": "One validation flag per line"}),
            "alteration_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (Prescription.Status.PENDING, Prescription.Status.PENDING.label),
            (Prescription.Status.UNDER_REVIEW, Prescription.Status.UNDER_REVIEW.label),
            (Prescription.Status.NEEDS_INFORMATION, Prescription.Status.NEEDS_INFORMATION.label),
            (Prescription.Status.APPROVED, Prescription.Status.APPROVED.label),
            (Prescription.Status.PARTIALLY_APPROVED, Prescription.Status.PARTIALLY_APPROVED.label),
            (Prescription.Status.REJECTED, Prescription.Status.REJECTED.label),
        ]
        for name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "class",
                "form-check-input" if name == "original_required_on_delivery" else "form-control",
            )
        self.fields["status"].widget.attrs["class"] = "form-select"

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        valid_until = cleaned.get("valid_until")
        if status == Prescription.Status.APPROVED and (
            not valid_until or valid_until < timezone.localdate()
        ):
            self.add_error("valid_until", "An approved prescription needs a current validity date.")
        if status == Prescription.Status.NEEDS_INFORMATION and not cleaned.get("clarification_message"):
            self.add_error(
                "clarification_message",
                "Explain what the customer needs to correct or provide.",
            )
        if status == Prescription.Status.REJECTED and not cleaned.get("rejection_reason"):
            self.add_error("rejection_reason", "A rejection reason is required.")
        return cleaned


class PrescriptionItemReviewForm(forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = [
            "product", "prescribed_name", "dosage", "duration_days", "instructions", "quantity",
            "fulfilled_quantity", "approval_status", "review_note",
        ]
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 2}),
            "duration_days": forms.NumberInput(attrs={"min": 1}),
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "fulfilled_quantity": forms.NumberInput(attrs={"min": 0}),
            "review_note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("approval_status") == PrescriptionItem.ApprovalStatus.APPROVED:
            if not str(cleaned.get("dosage") or "").strip():
                self.add_error("dosage", "Dosage is required before approving this medicine.")
            if (cleaned.get("duration_days") or 0) < 1:
                self.add_error("duration_days", "Duration in days is required before approval.")
            if (cleaned.get("quantity") or 0) < 1:
                self.add_error("quantity", "Approved quantity must be greater than zero.")
        return cleaned


PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemReviewForm,
    extra=1,
    can_delete=True,
)
