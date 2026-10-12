from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.forms import BootstrapFormMixin
from accounts.models import Address
from core.validators import validate_private_document
from extras.models import DoctorProfile

from .models import Consultation, Dependent, HealthRecord, LabBooking, LabCollectionSlot, LabTest, MedicationReminder


class DependentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Dependent
        fields = ["full_name", "relationship", "date_of_birth", "gender", "phone", "consent_at"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}), "consent_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class HealthRecordForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HealthRecord
        fields = ["dependent", "record_type", "title", "provider_name", "record_date", "document", "notes"]
        widgets = {"record_date": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dependent"].queryset = user.dependents.filter(is_active=True) if user else Dependent.objects.none()
        self.apply_bootstrap_classes()


class LabBookingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LabBooking
        fields = ["dependent", "lab_test", "address", "slot", "scheduled_start", "scheduled_end"]
        widgets = {"scheduled_start": forms.DateTimeInput(attrs={"type": "datetime-local"}), "scheduled_end": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, lab_test=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_lab_test_id = lab_test.pk if lab_test else None
        self.fields["dependent"].queryset = user.dependents.filter(is_active=True) if user else Dependent.objects.none()
        self.fields["address"].queryset = user.addresses.all() if user else Address.objects.none()
        self.fields["lab_test"].queryset = LabTest.objects.filter(
            is_active=True,
            partner__is_active=True,
        ).select_related("partner")
        if lab_test:
            self.fields["lab_test"].initial = lab_test
            self.fields["slot"].queryset = LabCollectionSlot.objects.filter(
                partner=lab_test.partner,
                is_active=True,
                is_blackout=False,
                starts_at__gte=timezone.now(),
            ).order_by("starts_at")
        else:
            self.fields["slot"].queryset = LabCollectionSlot.objects.filter(
                is_active=True,
                is_blackout=False,
                starts_at__gte=timezone.now(),
            ).order_by("starts_at")
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        test = cleaned.get("lab_test")
        slot = cleaned.get("slot")
        if test and slot and slot.partner_id != test.partner_id:
            self.add_error("slot", "Choose a collection slot offered by the selected lab partner.")
        if self.selected_lab_test_id and test and test.pk != self.selected_lab_test_id:
            self.add_error("lab_test", "The selected test cannot be changed from this booking link.")
        if slot and (slot.is_blackout or not slot.is_active or slot.available_capacity <= 0):
            self.add_error("slot", "That collection slot is no longer available.")
        return cleaned


class LabRescheduleForm(BootstrapFormMixin, forms.Form):
    slot = forms.ModelChoiceField(queryset=LabCollectionSlot.objects.none(), empty_label="Choose a new collection slot")

    def __init__(self, *args, booking=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.booking = booking
        if booking:
            self.fields["slot"].queryset = LabCollectionSlot.objects.filter(
                partner=booking.lab_test.partner,
                is_active=True,
                is_blackout=False,
                starts_at__gte=timezone.now(),
            ).exclude(pk=booking.slot_id).order_by("starts_at")
        self.apply_bootstrap_classes()

    def clean_slot(self):
        slot = self.cleaned_data["slot"]
        if slot.available_capacity <= 0:
            raise ValidationError("That collection slot is no longer available.")
        return slot


class MedicationReminderForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MedicationReminder
        fields = ["dependent", "product", "label", "dosage", "frequency", "next_due_at", "is_active"]
        widgets = {"next_due_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dependent"].queryset = user.dependents.filter(is_active=True) if user else Dependent.objects.none()
        self.fields["product"].queryset = self.fields["product"].queryset.filter(is_active=True)
        self.apply_bootstrap_classes()


class ConsultationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Consultation
        fields = ["dependent", "doctor", "mode", "symptoms", "patient_history", "consent_at", "scheduled_at"]
        widgets = {"symptoms": forms.Textarea(attrs={"rows": 5}), "patient_history": forms.Textarea(attrs={"rows": 4}), "consent_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dependent"].queryset = user.dependents.filter(is_active=True) if user else Dependent.objects.none()
        self.fields["doctor"].queryset = DoctorProfile.objects.filter(is_verified=True).order_by("full_name")
        self.apply_bootstrap_classes()


class ConsultationMessageForm(BootstrapFormMixin, forms.Form):
    message = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 4}))
    attachment = forms.FileField(required=False, validators=[validate_private_document])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
