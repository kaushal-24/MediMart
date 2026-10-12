from django import forms
from django.core.exceptions import ValidationError

from accounts.forms import BootstrapFormMixin

from .models import BlogPost, ContentIssue, DoctorProfile, SupportMessage, SupportTicket


MAX_SUPPORT_ATTACHMENT_SIZE = 5 * 1024 * 1024
ALLOWED_SUPPORT_ATTACHMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}


def validate_support_attachment(file):
    if not file:
        return file
    if file.size > MAX_SUPPORT_ATTACHMENT_SIZE:
        raise ValidationError("Attachment must be 5 MB or smaller.")
    content_type = getattr(file, "content_type", "")
    if content_type and content_type not in ALLOWED_SUPPORT_ATTACHMENT_TYPES:
        raise ValidationError("Upload a PDF, JPG, PNG, or WEBP attachment.")
    return file


class SupportTicketForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ["subject", "category", "message", "order_number", "attachment"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_attachment(self):
        return validate_support_attachment(self.cleaned_data.get("attachment"))


class SupportMessageForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SupportMessage
        fields = ["message", "attachment"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_attachment(self):
        return validate_support_attachment(self.cleaned_data.get("attachment"))


class DoctorProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DoctorProfile
        fields = [
            "full_name",
            "specialization",
            "registration_number",
            "medical_council",
            "qualification",
            "qualification_document",
            "experience_years",
            "clinic_name",
            "clinic_address",
            "phone",
            "consultation_fee",
            "availability",
        ]
        widgets = {
            "clinic_address": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class BlogPostForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ["title", "category", "image", "excerpt", "content", "status"]
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "content": forms.Textarea(attrs={"rows": 14}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class ContentIssueForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ContentIssue
        fields = ["issue_type", "details"]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 4, "placeholder": "Tell us what needs review and why."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
