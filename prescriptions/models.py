from django.conf import settings
from django.db import models
from django.urls import reverse
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
        NEEDS_INFORMATION = "needs_information", "More Information Required"
        PARTIALLY_APPROVED = "partially_approved", "Partially Approved"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class PatientGender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "not_stated", "Prefer not to say"

    class ScanStatus(models.TextChoices):
        PENDING = "pending", "Scan pending"
        COMPLETE = "complete", "Technical scan complete"
        NEEDS_REVIEW = "needs_review", "Needs manual review"
        FAILED = "failed", "Scan failed"

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
    patient_name = models.CharField(max_length=150, blank=True)
    patient_date_of_birth = models.DateField(blank=True, null=True)
    patient_gender = models.CharField(
        max_length=12,
        choices=PatientGender.choices,
        blank=True,
    )
    doctor_name = models.CharField(max_length=120, blank=True)
    doctor_registration_number = models.CharField(max_length=80, blank=True)
    clinic_name = models.CharField(max_length=160, blank=True)
    clinic_contact = models.CharField(max_length=120, blank=True)
    prescription_date = models.DateField(blank=True, null=True)
    valid_until = models.DateField(blank=True, null=True)
    max_fulfillments = models.PositiveIntegerField(default=1)
    fulfillment_count = models.PositiveIntegerField(default=0)
    requested_medicines = models.TextField(
        blank=True,
        help_text="Enter one medicine or requested item per line.",
    )
    notes = models.TextField(blank=True)
    customer_consent = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    clarification_message = models.TextField(blank=True)
    review_notes = models.TextField(blank=True)
    original_required_on_delivery = models.BooleanField(default=False)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="revisions",
        blank=True,
        null=True,
    )
    scan_status = models.CharField(max_length=20, choices=ScanStatus.choices, default=ScanStatus.PENDING)
    scan_summary = models.TextField(blank=True)
    scan_flags = models.JSONField(default=list, blank=True)
    scan_completed_at = models.DateTimeField(blank=True, null=True)
    prescriber_verified = models.BooleanField(default=False)
    patient_identity_verified = models.BooleanField(default=False)
    clinical_validation_status = models.CharField(max_length=30, default="pending")
    validation_flags = models.JSONField(default=list, blank=True)
    alteration_notes = models.TextField(blank=True)
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

    def get_absolute_url(self):
        return reverse("prescriptions:prescription_detail", args=[self.pk])

    def mark_approved(self, reviewer=None):
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = ""
        self.clarification_message = ""
        self.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "rejection_reason",
                "clarification_message",
                "updated_at",
            ]
        )
        self.items.filter(approval_status=PrescriptionItem.ApprovalStatus.PENDING).update(
            approval_status=PrescriptionItem.ApprovalStatus.APPROVED,
            reviewed_by=reviewer,
            reviewed_at=timezone.now(),
        )

    def mark_rejected(self, reviewer=None, reason=""):
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    def compute_validation_flags(self, items=None):
        """Return machine-readable blockers before a pharmacist can approve."""
        flags = []
        today = timezone.localdate()
        if not self.patient_name.strip():
            flags.append("patient_name_missing")
        if not self.prescription_date:
            flags.append("prescription_date_missing")
        elif self.prescription_date > today:
            flags.append("prescription_date_in_future")
        if not self.doctor_name.strip():
            flags.append("doctor_name_missing")
        if not self.doctor_registration_number.strip():
            flags.append("doctor_registration_missing")
        if self.scan_status == self.ScanStatus.FAILED:
            flags.append("document_scan_failed")
        if not self.prescriber_verified:
            flags.append("prescriber_not_verified")
        if not self.patient_identity_verified:
            flags.append("patient_identity_not_verified")
        if self.alteration_notes.strip():
            flags.append("prescription_alterations_recorded")

        item_list = list(items if items is not None else self.items.all())
        if not item_list and not self.requested_medicines.strip():
            flags.append("requested_medicines_missing")
        for item in item_list:
            if isinstance(item, dict):
                approved = item.get("approval_status") == PrescriptionItem.ApprovalStatus.APPROVED
                dosage = str(item.get("dosage") or "").strip()
                duration_days = item.get("duration_days") or 0
                quantity = item.get("quantity") or 0
            else:
                approved = item.approval_status == PrescriptionItem.ApprovalStatus.APPROVED
                dosage = item.dosage.strip()
                duration_days = item.duration_days
                quantity = item.quantity
            if approved and not dosage:
                flags.append("approved_item_dosage_missing")
            if approved and duration_days < 1:
                flags.append("approved_item_duration_missing")
            if approved and quantity < 1:
                flags.append("approved_item_quantity_invalid")
        return sorted(set(flags))

    def is_ready_for_approval(self, items=None):
        return not self.compute_validation_flags(items=items)

    @property
    def is_current(self):
        return bool(
            self.status in {self.Status.APPROVED, self.Status.PARTIALLY_APPROVED}
            and self.valid_until
            and self.valid_until >= timezone.localdate()
            and self.fulfillment_count < self.max_fulfillments
        )

    def authorizes(self, product, quantity=1):
        if not self.is_current:
            return False
        item = self.items.filter(product=product).first()
        return bool(
            item
            and item.approval_status == PrescriptionItem.ApprovalStatus.APPROVED
            and item.remaining_quantity >= quantity
        )

    @property
    def remaining_fulfillments(self):
        return max(0, self.max_fulfillments - self.fulfillment_count)

    @property
    def needs_customer_action(self):
        return self.status in {self.Status.NEEDS_INFORMATION, self.Status.REJECTED}


class PrescriptionItem(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CLARIFICATION = "clarification", "Needs clarification"

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
    duration_days = models.PositiveIntegerField(default=0)
    instructions = models.TextField(blank=True)
    quantity = models.PositiveIntegerField(default=1)
    fulfilled_quantity = models.PositiveIntegerField(default=0)
    approval_status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_prescription_items",
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)

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


class PrescriptionReview(models.Model):
    class Decision(models.TextChoices):
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        PARTIALLY_APPROVED = "partially_approved", "Partially approved"
        NEEDS_INFORMATION = "needs_information", "More information required"
        REJECTED = "rejected", "Rejected"

    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="review_history")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prescription_reviews")
    decision = models.CharField(max_length=30, choices=Decision.choices)
    pharmacy_license_number = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    validation_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Prescription #{self.prescription_id} - {self.get_decision_display()}"
