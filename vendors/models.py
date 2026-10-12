from django.conf import settings
from django.db import models
from django.utils import timezone

from core.storage import private_media_storage
from core.fields import EncryptedCharField
from core.validators import validate_private_document
from products.models import Product


class Vendor(models.Model):
    class BusinessType(models.TextChoices):
        PHARMACY = "pharmacy", "Pharmacy"
        MEDICAL_EQUIPMENT = "medical_equipment", "Medical Equipment Seller"
        SURGICAL_EQUIPMENT = "surgical_equipment", "Surgical Equipment Seller"
        DIAGNOSTIC_EQUIPMENT = "diagnostic_equipment", "Diagnostic Equipment Seller"
        MANUFACTURER = "manufacturer", "Equipment Manufacturer"
        GENERAL_HEALTHCARE = "general_healthcare", "General Healthcare Seller"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vendor_profile",
    )
    business_name = models.CharField(max_length=160)
    owner_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    gst_number = models.CharField(max_length=30, blank=True)
    license_number = models.CharField(max_length=60)
    business_type = models.CharField(max_length=40, choices=BusinessType.choices)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_number = EncryptedCharField(max_length=512, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    documents = models.FileField(
        upload_to="vendors/documents/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business_name"]
        indexes = [
            models.Index(fields=["is_approved", "is_active"], name="vendor_approval_active_idx"),
            models.Index(fields=["business_type", "is_active"], name="vendor_type_active_idx"),
        ]

    def __str__(self):
        return self.business_name

    @property
    def requires_regulatory_license(self):
        return self.business_type != self.BusinessType.GENERAL_HEALTHCARE

    @property
    def has_verified_license(self):
        today = timezone.localdate()
        return self.licenses.filter(
            status=BusinessLicense.Status.VERIFIED,
            valid_until__gte=today,
        ).exists()


class BusinessLicense(models.Model):
    class LicenseType(models.TextChoices):
        DRUG_RETAIL = "drug_retail", "Drug sale licence - retail"
        DRUG_WHOLESALE = "drug_wholesale", "Drug sale licence - wholesale"
        DRUG_MANUFACTURING = "drug_manufacturing", "Drug manufacturing licence"
        DEVICE_SALE = "device_sale", "Medical device sale registration (MD-42)"
        DEVICE_MANUFACTURING = "device_manufacturing", "Medical device manufacturing licence"
        DEVICE_IMPORT = "device_import", "Medical device import licence (MD-15)"
        OTHER = "other", "Other regulatory licence"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending manual review"
        MANUAL_REVIEW = "manual_review", "Manual review required"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    class VerificationSource(models.TextChoices):
        APPLICANT = "applicant", "Applicant supplied"
        ONDLS = "ondls", "ONDLS manual verification"
        CDSCO_MD = "cdsco_md", "CDSCO medical device portal"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="licenses")
    license_type = models.CharField(max_length=40, choices=LicenseType.choices)
    license_number = models.CharField(max_length=100)
    form_number = models.CharField(max_length=40, blank=True)
    legal_name = models.CharField(max_length=200, blank=True)
    premises_address = models.TextField(blank=True)
    state = models.CharField(max_length=100, blank=True)
    licensing_authority = models.CharField(max_length=200, blank=True)
    issued_on = models.DateField(blank=True, null=True)
    valid_until = models.DateField(blank=True, null=True)
    document = models.FileField(
        upload_to="vendors/licenses/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    verification_source = models.CharField(
        max_length=30,
        choices=VerificationSource.choices,
        default=VerificationSource.APPLICANT,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_business_licenses",
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "license_type", "license_number"],
                name="unique_vendor_business_license",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "license_type"], name="license_status_type_idx"),
            models.Index(fields=["license_number"], name="license_number_idx"),
            models.Index(fields=["vendor", "status"], name="license_vendor_status_idx"),
        ]

    def __str__(self):
        return f"{self.vendor.business_name} - {self.license_number}"

    def is_compatible_with(self, regulation_type):
        compatible_types = {
            Product.RegulationType.DRUG_SALE: {
                self.LicenseType.DRUG_RETAIL,
                self.LicenseType.DRUG_WHOLESALE,
            },
            Product.RegulationType.MEDICAL_DEVICE_SALE: {
                self.LicenseType.DEVICE_SALE,
                self.LicenseType.DEVICE_MANUFACTURING,
                self.LicenseType.DEVICE_IMPORT,
            },
            Product.RegulationType.MEDICAL_DEVICE_MANUFACTURE: {
                self.LicenseType.DEVICE_MANUFACTURING,
            },
            Product.RegulationType.MEDICAL_DEVICE_IMPORT: {self.LicenseType.DEVICE_IMPORT},
        }
        return bool(
            self.status == self.Status.VERIFIED
            and self.valid_until
            and self.valid_until >= timezone.localdate()
            and self.license_type in compatible_types.get(regulation_type, set())
        )

    @property
    def is_current(self):
        return bool(
            self.status == self.Status.VERIFIED
            and self.valid_until
            and self.valid_until >= timezone.localdate()
        )


class VendorProduct(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="vendor_products")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="vendor_products")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    delivery_time = models.CharField(max_length=80, default="2-4 days")
    warranty = models.CharField(max_length=120, blank=True)
    offer_text = models.CharField(max_length=160, blank=True)
    seller_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "product"],
                name="unique_vendor_product_offer",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="vendor_product_price_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["vendor", "is_approved", "is_active"],
                name="offer_vendor_status_idx",
            ),
            models.Index(
                fields=["product", "is_approved", "price"],
                name="offer_product_price_idx",
            ),
        ]

    def __str__(self):
        return f"{self.vendor.business_name} - {self.product.name}"

    @property
    def stock_status(self):
        if self.stock_quantity == 0:
            return "Out of Stock"
        if self.stock_quantity <= 5:
            return "Low Stock"
        return "In Stock"
