from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from .models import Address, UserProfile


User = get_user_model()


def _normalise_phone(value):
    """Return a comparable phone value while accepting common Indian formats."""
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def _resolve_login_identifier(identifier):
    """Resolve a login identifier without exposing whether an account exists."""
    value = str(identifier or "").strip()
    if not value:
        return None

    user = User.objects.filter(username__iexact=value).first()
    if user:
        return user

    user = User.objects.filter(email__iexact=value).first()
    if user:
        return user

    normalised_phone = _normalise_phone(value)
    if len(normalised_phone) < 10:
        return None

    phone_matches = [
        profile.user
        for profile in UserProfile.objects.select_related("user").filter(
            user__is_active=True,
            phone_number__isnull=False,
        )
        if _normalise_phone(profile.phone_number) == normalised_phone
    ]
    # Never guess when more than one account has the same phone number.
    return phone_matches[0] if len(phone_matches) == 1 else None


class BootstrapFormMixin:
    """Apply Bootstrap classes without adding a template dependency."""

    def apply_bootstrap_classes(self):
        for field_name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", "form-control")
            else:
                widget.attrs.setdefault("class", "form-control")


class UserRegistrationForm(BootstrapFormMixin, UserCreationForm):
    role = forms.ChoiceField(
        choices=[
            (UserProfile.Role.CUSTOMER, "Customer"),
            (UserProfile.Role.VENDOR, "Vendor"),
            (UserProfile.Role.MANUFACTURER, "Equipment Manufacturer"),
            (UserProfile.Role.PHARMACY, "Pharmacy"),
            (UserProfile.Role.DOCTOR, "Doctor"),
        ],
        help_text="Delivery staff and admin accounts should be created by the site owner.",
    )
    phone_number = forms.CharField(max_length=20, required=False)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "role",
            "password1",
            "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {"autocomplete": "email", "placeholder": "name@example.com"}
        )
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self.apply_bootstrap_classes()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]

        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data.get("role", UserProfile.Role.CUSTOMER),
                phone_number=self.cleaned_data.get("phone_number", ""),
            )

        return user


class CustomerRegistrationForm(UserRegistrationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("role", None)


class ProfessionalRegistrationForm(UserRegistrationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [
            (UserProfile.Role.VENDOR, "Healthcare seller"),
            (UserProfile.Role.MANUFACTURER, "Equipment manufacturer"),
            (UserProfile.Role.PHARMACY, "Licensed pharmacy"),
            (UserProfile.Role.DOCTOR, "Doctor"),
        ]
        self.fields["role"].help_text = (
            "Professional capabilities remain limited until the required business or identity review is complete."
        )


class UserProfileForm(BootstrapFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    phone_number = forms.CharField(max_length=20, required=False)
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    gender = forms.ChoiceField(
        choices=[("", "Select gender")] + list(UserProfile.Gender.choices),
        required=False,
    )
    profile_picture = forms.ImageField(required=False)

    def __init__(self, *args, user=None, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = profile
        if user and profile and not self.is_bound:
            self.initial.update(
                {
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "phone_number": profile.phone_number,
                    "date_of_birth": profile.date_of_birth,
                    "gender": profile.gender,
                }
            )
        self.apply_bootstrap_classes()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.email = self.cleaned_data["email"]
        self.user.save()

        self.profile.phone_number = self.cleaned_data["phone_number"]
        self.profile.date_of_birth = self.cleaned_data["date_of_birth"]
        self.profile.gender = self.cleaned_data["gender"]
        if self.cleaned_data.get("profile_picture"):
            self.profile.profile_picture = self.cleaned_data["profile_picture"]
        self.profile.save()

        return self.user


class AddressForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "full_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "house_number",
            "road",
            "neighbourhood",
            "suburb",
            "locality",
            "subdistrict",
            "district",
            "city",
            "state",
            "pincode",
            "landmark",
            "country",
            "country_code",
            "latitude",
            "longitude",
            "geocoding_place_id",
            "geocoding_osm_type",
            "geocoding_osm_id",
            "geocoding_display_name",
            "geocoding_payload",
            "location_source",
            "address_type",
            "is_default",
        ]
        widgets = {
            "road": forms.HiddenInput(),
            "neighbourhood": forms.HiddenInput(),
            "suburb": forms.HiddenInput(),
            "locality": forms.HiddenInput(),
            "subdistrict": forms.HiddenInput(),
            "country": forms.HiddenInput(),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
            "country_code": forms.HiddenInput(),
            "geocoding_place_id": forms.HiddenInput(),
            "geocoding_osm_type": forms.HiddenInput(),
            "geocoding_osm_id": forms.HiddenInput(),
            "geocoding_display_name": forms.HiddenInput(),
            "geocoding_payload": forms.HiddenInput(),
            "location_source": forms.HiddenInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not self.is_bound and not self.instance.pk:
            profile = getattr(user, "profile", None)
            self.initial.setdefault("full_name", user.get_full_name() or user.username)
            self.initial.setdefault("phone", getattr(profile, "phone_number", ""))
            self.initial.setdefault("country", "India")
            self.initial.setdefault("country_code", "in")
        self.apply_bootstrap_classes()


class StyledAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username, email, or phone number"
        self.fields["username"].widget.attrs.update(
            {
                "autocomplete": "username",
                "placeholder": "Enter username, email, or phone number",
                "inputmode": "text",
            }
        )
        self.fields["password"].widget.attrs.update(
            {"autocomplete": "current-password", "placeholder": "Password"}
        )
        self.apply_bootstrap_classes()

    def clean_username(self):
        identifier = self.cleaned_data["username"].strip()
        user = _resolve_login_identifier(identifier)
        return user.username if user else identifier


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class StyledPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class StyledSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
