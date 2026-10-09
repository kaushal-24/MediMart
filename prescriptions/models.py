from django.conf import settings
from django.db import models
from django.utils import timezone

from core.storage import private_media_storage
from core.validators import validate_private_document
from products.models import Product


def validate_prescription_file(value):
    """Backward-compatible validator path retained for historical migrations."""
    return validate_private_document(value)


class Prescription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    file = models.FileField(
        upload_to="prescriptions/",
        storage=private_media_storage,
        validators=[validate_private_document],
    )
    doctor_name = models.CharField(max_length=120, blank=True)
    doctor_registration_number = models.CharField(max_length=80, blank=True)
    prescription_date = models.DateField(blank=True, null=True)
    valid_until = models.DateField(blank=True, null=True)
    max_fulfillments = models.PositiveIntegerField(default=1)
    fulfillment_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_prescriptions",
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Prescription #{self.pk} - {self.user.username}"

    def mark_approved(self, reviewer=None):
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    def mark_rejected(self, reviewer=None, reason=""):
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    @property
    def is_current(self):
        return bool(
            self.status == self.Status.APPROVED
            and self.valid_until
            and self.valid_until >= timezone.localdate()
            and self.fulfillment_count < self.max_fulfillments
        )

    def authorizes(self, product, quantity=1):
        if not self.is_current:
            return False
        item = self.items.filter(product=product).first()
        return bool(item and item.remaining_quantity >= quantity)


class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="prescription_items",
    )
    prescribed_name = models.CharField(max_length=180, blank=True)
    dosage = models.CharField(max_length=160, blank=True)
    instructions = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    fulfilled_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prescription", "product"],
                name="unique_prescription_product",
            ),
            models.CheckConstraint(
                condition=models.Q(fulfilled_quantity__lte=models.F("quantity")),
                name="prescription_fulfilled_lte_quantity",
            ),
        ]

    def __str__(self):
        return f"{self.prescription} - {self.product.name}"

    @property
    def remaining_quantity(self):
        return max(0, self.quantity - self.fulfilled_quantity)
