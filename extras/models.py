from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.storage import private_media_storage
from core.validators import validate_private_document, validate_public_image


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        ORDER = "order", "Order"
        PRESCRIPTION = "prescription", "Prescription"
        COUPON = "coupon", "Coupon"
        OFFER = "offer", "Offer"
        SUPPORT = "support", "Support"
        GENERAL = "general", "General"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=140)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
    )
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class NotificationDelivery(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices)
    destination = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(blank=True, null=True)
    last_error = models.CharField(max_length=500, blank=True)
    provider_reference = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "notification deliveries"
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "channel", "destination"],
                name="unique_notification_delivery",
            )
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="notification_queue_idx")
        ]

    def __str__(self):
        return f"{self.notification_id}: {self.channel} to {self.destination}"


class SupportTicket(models.Model):
    class Category(models.TextChoices):
        ORDER = "order", "Order"
        PRESCRIPTION = "prescription", "Prescription"
        PAYMENT = "payment", "Payment"
        PRODUCT = "product", "Product"
        ACCOUNT = "account", "Account"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_tickets",
    )
    subject = models.CharField(max_length=180)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    message = models.TextField()
    order_number = models.CharField(max_length=30, blank=True)
    attachment = models.FileField(
        upload_to="support/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.subject


class SupportMessage(models.Model):
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_messages",
    )
    message = models.TextField()
    attachment = models.FileField(
        upload_to="support/replies/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    is_staff_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Reply on {self.ticket.subject}"


class BlogCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "blog categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("extras:blog_category", kwargs={"slug": self.slug})


class BlogPost(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    image = models.ImageField(
        upload_to="blog/",
        blank=True,
        null=True,
        validators=[validate_public_image],
    )
    excerpt = models.CharField(max_length=255, blank=True)
    content = models.TextField()
    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL,
        related_name="posts",
        blank=True,
        null=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="blog_posts",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(blank=True, null=True)
    reviewer_name = models.CharField(max_length=160, blank=True)
    reviewer_credentials = models.CharField(max_length=255, blank=True)
    source_references = models.TextField(blank=True)
    last_reviewed_at = models.DateTimeField(blank=True, null=True)
    review_due_at = models.DateTimeField(blank=True, null=True)
    correction_note = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("extras:blog_detail", kwargs={"slug": self.slug})

    @property
    def estimated_read_minutes(self):
        return max(1, round(len(self.content.split()) / 200))


class ContentIssue(models.Model):
    class IssueType(models.TextChoices):
        INCORRECT = "incorrect", "Incorrect information"
        OUTDATED = "outdated", "Outdated information"
        SAFETY = "safety", "Safety concern"
        TYPO = "typo", "Typo or formatting"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In review"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="content_issues",
        blank=True,
        null=True,
    )
    blog_post = models.ForeignKey(
        BlogPost,
        on_delete=models.CASCADE,
        related_name="content_issues",
        blank=True,
        null=True,
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="content_issues",
        blank=True,
        null=True,
    )
    issue_type = models.CharField(max_length=20, choices=IssueType.choices)
    details = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    reviewer_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_content_issues",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(blog_post__isnull=False) | models.Q(product__isnull=False)),
                name="content_issue_has_content",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="content_issue_queue_idx"),
        ]

    def __str__(self):
        subject = self.blog_post or self.product or "content"
        return f"{self.get_issue_type_display()} on {subject}"


class DoctorProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    full_name = models.CharField(max_length=160)
    specialization = models.CharField(max_length=140)
    registration_number = models.CharField(max_length=100, blank=True)
    medical_council = models.CharField(max_length=160, blank=True)
    qualification = models.CharField(max_length=200, blank=True)
    qualification_document = models.FileField(
        upload_to="doctors/credentials/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    experience_years = models.PositiveIntegerField(default=0)
    clinic_name = models.CharField(max_length=160, blank=True)
    clinic_address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    availability = models.CharField(
        max_length=180,
        blank=True,
        help_text="Example: Mon-Fri, 10 AM to 5 PM",
    )
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="verified_doctors",
        blank=True,
        null=True,
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(consultation_fee__gte=0),
                name="doctor_consultation_fee_nonnegative",
            )
        ]

    def __str__(self):
        return self.full_name


class PharmacistProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pharmacist_profile",
    )
    full_name = models.CharField(max_length=160)
    registration_number = models.CharField(max_length=100)
    licensing_authority = models.CharField(max_length=180, blank=True)
    pharmacy_name = models.CharField(max_length=180)
    pharmacy_license_number = models.CharField(max_length=120)
    state = models.CharField(max_length=100)
    credential_document = models.FileField(
        upload_to="pharmacists/credentials/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="verified_pharmacists",
        blank=True,
        null=True,
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["is_verified", "state"], name="pharmacist_verified_state_idx"),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.pharmacy_name}"


class QualityComplaint(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under review"
        ESCALATED = "escalated", "Escalated"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quality_complaints")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="quality_complaints")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, related_name="quality_complaints", blank=True, null=True)
    batch_number = models.CharField(max_length=80, blank=True)
    description = models.TextField()
    evidence = models.FileField(
        upload_to="quality-complaints/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolution_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_quality_complaints",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quality complaint #{self.pk} - {self.product.name}"
