from django import forms
from django.core.exceptions import ValidationError

from .models import Review


MAX_REVIEW_IMAGE_SIZE = 3 * 1024 * 1024
ALLOWED_REVIEW_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "title", "comment", "image"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["rating"].widget.attrs.update({"min": 1, "max": 5})

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        if image.size > MAX_REVIEW_IMAGE_SIZE:
            raise ValidationError("Review image must be 3 MB or smaller.")
        content_type = getattr(image, "content_type", "")
        if content_type and content_type not in ALLOWED_REVIEW_IMAGE_TYPES:
            raise ValidationError("Upload a JPG, PNG, or WEBP review image.")
        return image


class ReviewAbuseReportForm(forms.Form):
    reason = forms.CharField(max_length=255, min_length=5, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Tell us what is wrong"}))


class SellerReplyForm(forms.Form):
    reply = forms.CharField(min_length=5, max_length=2000, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))
