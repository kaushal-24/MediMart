from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from uuid import uuid4

from accounts.models import Address
from core.storage import private_media_storage
from core.validators import validate_private_document


class Dependent(models.Model):
    class Relationship(models.TextChoices):
        SELF = "self", "Self"
        SPOUSE = "spouse", "Spouse"
        CHILD = "child", "Child"
        PARENT = "parent", "Parent"
        OTHER = "other", "Other"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dependents")
    full_name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=20, choices=Relationship.choices, default=Relationship.OTHER)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    consent_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "full_name", "date_of_birth"],
                name="unique_user_dependent_identity",
            )
        ]

    def __str__(self):
        return f"{self.full_name} ({self.get_relationship_display()})"


class HealthRecord(models.Model):
    class RecordType(models.TextChoices):
        PRESCRIPTION = "prescription", "Prescription"
        LAB_REPORT = "lab_report", "Lab report"
        DISCHARGE = "discharge", "Discharge summary"
        IMAGING = "imaging", "Imaging"
        VACCINATION = "vaccination", "Vaccination"
        OTHER = "other", "Other"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="health_records")
    dependent = models.ForeignKey(
        Dependent,
        on_delete=models.CASCADE,
        related_name="health_records",
        blank=True,
        null=True,
    )
    record_type = models.CharField(max_length=20, choices=RecordType.choices, default=RecordType.OTHER)
    title = models.CharField(max_length=180)
    provider_name = models.CharField(max_length=180, blank=True)
    record_date = models.DateField(blank=True, null=True)
    document = models.FileField(
        upload_to="health-records/",
        storage=private_media_storage,
        validators=[validate_private_document],
    )
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-record_date", "-created_at"]

    def __str__(self):
        return self.title


class HealthRecordShare(models.Model):
    record = models.ForeignKey(HealthRecord, on_delete=models.CASCADE, related_name="shares")
    shared_with = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shared_health_records")
    purpose = models.CharField(max_length=255)
    consented_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="health_record_consents")
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-granted_at"]

    @property
    def is_active(self):
        return not self.revoked_at and self.expires_at >= timezone.now()


class LabPartner(models.Model):
    name = models.CharField(max_length=180)
    city = models.CharField(max_length=100)
    address = models.TextField()
    accreditations = models.CharField(max_length=255, blank=True)
    licence_number = models.CharField(max_length=120, blank=True)
    quality_document = models.FileField(
        upload_to="healthcare/labs/quality/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    operating_hours = models.JSONField(default=dict, blank=True)
    service_area_pincodes = models.TextField(blank=True, help_text="Comma-separated serviceable pincodes.")
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "city"]

    def __str__(self):
        return f"{self.name} - {self.city}"


class LabBranch(models.Model):
    partner = models.ForeignKey(LabPartner, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=180)
    address = models.TextField()
    city = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10, db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    operating_hours = models.JSONField(default=dict, blank=True)
    service_area_pincodes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["partner__name", "city", "name"]

    def __str__(self):
        return f"{self.partner.name} - {self.name}"


class LabTest(models.Model):
    class Category(models.TextChoices):
        TEST = "test", "Individual test"
        PACKAGE = "package", "Health package"
        SCAN = "scan", "Scan"
        VACCINATION = "vaccination", "Vaccination"

    partner = models.ForeignKey(LabPartner, on_delete=models.PROTECT, related_name="tests")
    name = models.CharField(max_length=180)
    image = models.ImageField(
        upload_to="healthcare/lab-tests/",
        blank=True,
        null=True,
        help_text="Optional image for this test or package. Use a clear, non-sensitive healthcare image.",
    )
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.TEST)
    description = models.TextField(blank=True)
    sample_type = models.CharField(max_length=100, blank=True)
    preparation = models.TextField(blank=True)
    what_it_measures = models.TextField(blank=True)
    limitations = models.TextField(blank=True)
    included_test_count = models.PositiveIntegerField(default=1)
    report_sla_hours = models.PositiveIntegerField(default=48)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    mrp = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    is_home_collection = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__lte=models.F("mrp")), name="lab_price_lte_mrp")
        ]

    def __str__(self):
        return self.name


class LabBooking(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        CONFIRMED = "confirmed", "Confirmed"
        SAMPLE_COLLECTED = "sample_collected", "Sample collected"
        PROCESSING = "processing", "Processing"
        REPORT_READY = "report_ready", "Report ready"
        RECOLLECTION = "recollection", "Recollection required"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lab_bookings")
    dependent = models.ForeignKey(Dependent, on_delete=models.PROTECT, related_name="lab_bookings", blank=True, null=True)
    lab_test = models.ForeignKey(LabTest, on_delete=models.PROTECT, related_name="bookings")
    slot = models.ForeignKey("LabCollectionSlot", on_delete=models.PROTECT, related_name="bookings", blank=True, null=True)
    phlebotomist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="phlebotomy_bookings", blank=True, null=True)
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="lab_bookings")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REQUESTED)
    scheduled_start = models.DateTimeField(blank=True, null=True)
    scheduled_end = models.DateTimeField(blank=True, null=True)
    collection_otp = models.CharField(max_length=8, blank=True)
    identity_verified_at = models.DateTimeField(blank=True, null=True)
    collection_proof = models.FileField(upload_to="healthcare/collection-proof/", storage=private_media_storage, validators=[validate_private_document], blank=True, null=True)
    sample_collected_at = models.DateTimeField(blank=True, null=True)
    accession_number = models.CharField(max_length=80, blank=True, unique=True)
    report_file = models.FileField(
        upload_to="lab-reports/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    report_summary = models.TextField(blank=True)
    report_ready_at = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.accession_number:
            self.accession_number = f"LAB{uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lab_test.name} booking #{self.pk}"


class LabCollectionSlot(models.Model):
    partner = models.ForeignKey(LabPartner, on_delete=models.PROTECT, related_name="collection_slots")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=1)
    booked_count = models.PositiveIntegerField(default=0)
    is_blackout = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="lab_slot_end_after_start"),
            models.CheckConstraint(condition=models.Q(booked_count__lte=models.F("capacity")), name="lab_slot_booked_lte_capacity"),
        ]

    @property
    def available_capacity(self):
        return max(0, self.capacity - self.booked_count)


class LabSampleEvent(models.Model):
    class EventType(models.TextChoices):
        REQUESTED = "requested", "Booking requested"
        CANCELLED = "cancelled", "Booking cancelled"
        COLLECTED = "collected", "Collected"
        HANDED_TO_COURIER = "handed_to_courier", "Handed to courier"
        RECEIVED_AT_LAB = "received_at_lab", "Received at lab"
        PROCESSING = "processing", "Processing"
        RECOLLECTION = "recollection", "Recollection required"
        DISPOSED = "disposed", "Disposed"

    booking = models.ForeignKey(LabBooking, on_delete=models.CASCADE, related_name="sample_events")
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    barcode = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=180, blank=True)
    note = models.TextField(blank=True)
    proof = models.FileField(upload_to="healthcare/sample-events/", storage=private_media_storage, validators=[validate_private_document], blank=True, null=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="sample_events_recorded")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class LabReportValue(models.Model):
    booking = models.ForeignKey(LabBooking, on_delete=models.CASCADE, related_name="report_values")
    test_name = models.CharField(max_length=180)
    value = models.CharField(max_length=120)
    unit = models.CharField(max_length=60, blank=True)
    reference_range = models.CharField(max_length=120, blank=True)
    reference_range_rule = models.ForeignKey("LabReferenceRange", on_delete=models.SET_NULL, blank=True, null=True, related_name="report_values")
    abnormal_flag = models.CharField(max_length=30, blank=True)
    medically_reviewed = models.BooleanField(default=False)
    explanation = models.TextField(blank=True, help_text="Reviewed, non-diagnostic explanation for this result.")
    explanation_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_lab_explanations",
        blank=True,
        null=True,
    )
    explanation_reviewed_at = models.DateTimeField(blank=True, null=True)
    corrected_from = models.ForeignKey("self", on_delete=models.SET_NULL, blank=True, null=True, related_name="corrections")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_display_reference_range(self):
        return self.reference_range_rule.range_text if self.reference_range_rule_id else self.reference_range


class LabReferenceRange(models.Model):
    """Age/sex-aware reference information maintained by an approved lab partner."""

    class Sex(models.TextChoices):
        ANY = "any", "Any"
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    lab_test = models.ForeignKey(LabTest, on_delete=models.CASCADE, related_name="reference_ranges")
    test_name = models.CharField(max_length=180)
    sex = models.CharField(max_length=10, choices=Sex.choices, default=Sex.ANY)
    min_age_years = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    max_age_years = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    range_text = models.CharField(max_length=180)
    unit = models.CharField(max_length=60, blank=True)
    source_note = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="reviewed_lab_ranges")
    reviewed_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["lab_test__name", "test_name", "sex", "min_age_years"]
        indexes = [models.Index(fields=["lab_test", "sex", "is_active"], name="lab_range_test_sex_idx")]

    def __str__(self):
        return f"{self.lab_test.name}: {self.test_name} ({self.range_text})"


class LabInvoice(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"
        VOID = "void", "Void"

    booking = models.OneToOneField(LabBooking, on_delete=models.PROTECT, related_name="invoice")
    invoice_number = models.CharField(max_length=40, unique=True, editable=False)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ISSUED)
    issued_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-issued_at"]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"LAB-INV-{uuid4().hex[:10].upper()}"
        if not self.total_amount:
            self.total_amount = max(0, self.subtotal + self.tax_amount - self.discount_amount)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number


class LabRefund(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        PROCESSED = "processed", "Processed"
        REJECTED = "rejected", "Rejected"

    invoice = models.ForeignKey(LabInvoice, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="reviewed_lab_refunds")
    gateway_reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LabSettlement(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEW = "review", "Under review"
        PAID = "paid", "Paid"
        DISPUTED = "disputed", "Disputed"

    partner = models.ForeignKey(LabPartner, on_delete=models.PROTECT, related_name="settlements")
    period_start = models.DateField()
    period_end = models.DateField()
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LabDispute(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    booking = models.ForeignKey(LabBooking, on_delete=models.PROTECT, related_name="disputes")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lab_disputes")
    category = models.CharField(max_length=80)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="resolved_lab_disputes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Consultation(models.Model):
    class Mode(models.TextChoices):
        CHAT = "chat", "Chat"
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        CONFIRMED = "confirmed", "Confirmed"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REFUND_PENDING = "refund_pending", "Refund pending"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="consultations")
    dependent = models.ForeignKey(Dependent, on_delete=models.PROTECT, related_name="consultations", blank=True, null=True)
    doctor = models.ForeignKey("extras.DoctorProfile", on_delete=models.PROTECT, related_name="consultations")
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.CHAT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    symptoms = models.TextField()
    patient_history = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    current_medicines = models.TextField(blank=True)
    red_flag_screening = models.JSONField(default=dict, blank=True)
    emergency_guidance = models.TextField(blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    consent_at = models.DateTimeField(blank=True, null=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    followup_until = models.DateTimeField(blank=True, null=True)
    clinical_notes = models.TextField(blank=True)
    advice = models.TextField(blank=True)
    e_prescription = models.FileField(
        upload_to="consultations/prescriptions/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Consultation #{self.pk} with {self.doctor.full_name}"


class DoctorAvailability(models.Model):
    doctor = models.ForeignKey("extras.DoctorProfile", on_delete=models.CASCADE, related_name="availability_slots")
    weekday = models.PositiveSmallIntegerField(help_text="Monday=0 through Sunday=6")
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_minutes = models.PositiveIntegerField(default=30)
    capacity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["doctor__full_name", "weekday", "start_time"]
        constraints = [models.CheckConstraint(condition=models.Q(weekday__lte=6), name="doctor_availability_weekday_lte_6")]


class ConsultationPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        REFUND_PENDING = "refund_pending", "Refund pending"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    consultation = models.OneToOneField(Consultation, on_delete=models.PROTECT, related_name="payment")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=40, default="razorpay")
    provider_order_id = models.CharField(max_length=120, blank=True)
    provider_payment_id = models.CharField(max_length=120, blank=True)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    failure_reason = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class ConsultationFollowUp(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name="follow_ups")
    scheduled_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[("scheduled", "Scheduled"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="scheduled")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_consultation_followups")
    created_at = models.DateTimeField(auto_now_add=True)


class ConsultationMessage(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="consultation_messages")
    message = models.TextField()
    attachment = models.FileField(
        upload_to="consultations/attachments/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message for consultation #{self.consultation_id}"


class MedicationReminder(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="medication_reminders")
    dependent = models.ForeignKey(Dependent, on_delete=models.CASCADE, related_name="medication_reminders", blank=True, null=True)
    product = models.ForeignKey("products.Product", on_delete=models.SET_NULL, related_name="medication_reminders", blank=True, null=True)
    label = models.CharField(max_length=180)
    dosage = models.CharField(max_length=120, blank=True)
    frequency = models.CharField(max_length=120)
    next_due_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    last_notified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_due_at"]

    def __str__(self):
        return self.label


