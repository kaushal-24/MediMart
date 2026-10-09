from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from core.validators import validate_public_image
from core.fields import EncryptedCharField


class UserProfile(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        VENDOR = "vendor", "Vendor"
        MANUFACTURER = "manufacturer", "Manufacturer"
        PHARMACY = "pharmacy", "Pharmacy"
        DOCTOR = "doctor", "Doctor"
        DELIVERY_STAFF = "delivery_staff", "Delivery Staff"
        SUPPORT_STAFF = "support_staff", "Support Staff"
        COMPLIANCE_OFFICER = "compliance_officer", "Compliance Officer"
        CATALOG_MANAGER = "catalog_manager", "Catalog Manager"
        OPERATIONS_MANAGER = "operations_manager", "Operations Manager"
        WAREHOUSE_MANAGER = "warehouse_manager", "Warehouse Manager"
        ADMIN = "admin", "Admin"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    profile_picture = models.ImageField(
        upload_to="profile/",
        blank=True,
        null=True,
        validators=[validate_public_image],
    )
    preferred_location_label = models.CharField(max_length=255, blank=True)
    preferred_city = models.CharField(max_length=100, blank=True)
    preferred_state = models.CharField(max_length=100, blank=True)
    preferred_pincode = models.CharField(max_length=10, blank=True)
    preferred_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )
    preferred_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
    )
    location_updated_at = models.DateTimeField(blank=True, null=True)
    mfa_secret = EncryptedCharField(max_length=512, blank=True)
    mfa_enabled = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["role"], name="profile_role_idx"),
            models.Index(fields=["preferred_pincode"], name="profile_pincode_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} profile"


class Address(models.Model):
    class AddressType(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    class LocationSource(models.TextChoices):
        MANUAL = "manual", "Entered manually"
        GEOLOCATION = "geolocation", "Detected from device"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    house_number = models.CharField(max_length=40, blank=True)
    road = models.CharField(max_length=160, blank=True)
    neighbourhood = models.CharField(max_length=160, blank=True)
    suburb = models.CharField(max_length=160, blank=True)
    locality = models.CharField(max_length=160, blank=True)
    subdistrict = models.CharField(max_length=160, blank=True)
    district = models.CharField(max_length=160, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(
        max_length=10,
        validators=[RegexValidator(r"^\d{6}$", "Enter a valid 6-digit Indian pincode.")],
    )
    landmark = models.CharField(max_length=150, blank=True)
    country = models.CharField(max_length=100, default="India")
    country_code = models.CharField(max_length=2, default="in")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    geocoding_place_id = models.CharField(max_length=80, blank=True)
    geocoding_osm_type = models.CharField(max_length=20, blank=True)
    geocoding_osm_id = models.CharField(max_length=80, blank=True)
    geocoding_display_name = models.TextField(blank=True)
    geocoding_payload = models.JSONField(default=dict, blank=True)
    location_source = models.CharField(
        max_length=20,
        choices=LocationSource.choices,
        default=LocationSource.MANUAL,
    )
    address_type = models.CharField(
        max_length=10,
        choices=AddressType.choices,
        default=AddressType.HOME,
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-updated_at"]
        verbose_name_plural = "addresses"
        indexes = [
            models.Index(fields=["user", "is_default"], name="address_user_default_idx"),
            models.Index(fields=["pincode"], name="address_pincode_idx"),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.city} ({self.pincode})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )
