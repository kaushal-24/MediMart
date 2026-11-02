from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        blank=True,
        null=True,
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100, blank=True)
    summary = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id", "-created_at"], name="audit_target_created_idx"),
            models.Index(fields=["actor", "-created_at"], name="audit_actor_created_idx"),
            models.Index(fields=["action", "-created_at"], name="audit_action_created_idx"),
        ]

    def __str__(self):
        return f"{self.action}: {self.summary}"


class ApprovalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    action = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approval_requests")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="approval_decisions")
    request_reason = models.TextField(blank=True)
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["status", "created_at"]
        constraints = [models.UniqueConstraint(fields=["content_type", "object_id", "action", "status"], name="approval_target_action_status_unique")]
        indexes = [models.Index(fields=["status", "created_at"], name="approval_status_created_idx")]

    def __str__(self):
        return f"{self.action} #{self.object_id} ({self.get_status_display()})"


class CheckoutSettings(models.Model):
    """Database overrides for customer-visible checkout charges and COD rules."""

    delivery_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=49,
        validators=[MinValueValidator(0)],
    )
    free_delivery = models.BooleanField(default=False)
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    handling_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    platform_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    cold_chain_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    cod_max_order_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=5000,
        validators=[MinValueValidator(0)],
    )
    cod_blocked_pincodes = models.TextField(
        blank=True,
        help_text="Enter blocked 6-digit pincodes separated by commas or new lines.",
    )
    finance_test_mode = models.BooleanField(
        default=True,
        help_text="Keep finance integrations and settlement actions in test mode until approved for live use.",
    )
    gst_enabled = models.BooleanField(default=True)
    gstin = models.CharField(max_length=20, blank=True)
    business_state = models.CharField(max_length=100, blank=True, default="Gujarat")
    invoice_prefix = models.CharField(max_length=20, default="MM-INV")
    commission_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    settlement_days = models.PositiveIntegerField(default=7)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="updated_checkout_settings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "checkout settings"
        verbose_name_plural = "checkout settings"

    def __str__(self):
        return "MediMart checkout settings"
