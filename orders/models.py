from decimal import Decimal
from datetime import timedelta
import secrets
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address
from core.storage import private_media_storage
from core.validators import validate_private_document
from products.models import Product
from vendors.models import Vendor, VendorProduct


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed Amount"

    code = models.CharField(max_length=30, unique=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maximum_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    start_date = models.DateField()
    end_date = models.DateField()
    usage_limit = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code

    def calculate_discount(self, subtotal):
        if subtotal < self.minimum_order:
            return Decimal("0.00")
        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = subtotal * (self.discount_value / Decimal("100"))
        else:
            discount = self.discount_value
        if self.maximum_discount:
            discount = min(discount, self.maximum_discount)
        return min(discount, subtotal)


class Order(models.Model):
    class PaymentMethod(models.TextChoices):
        COD = "cod", "Cash on Delivery"
        RAZORPAY = "razorpay", "Razorpay Online Payment"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        AUTHORIZED = "authorized", "Authorized"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"
        REFUNDED = "refunded", "Refunded"

    class OrderStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        RETURNED = "returned", "Returned"
        REFUNDED = "refunded", "Refunded"

    order_number = models.CharField(max_length=30, unique=True, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="orders")
    delivery_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_delivery_orders",
        blank=True,
        null=True,
    )
    address_snapshot = models.TextField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        related_name="orders",
        blank=True,
        null=True,
    )
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    stock_reserved_until = models.DateTimeField(blank=True, null=True)
    inventory_released_at = models.DateTimeField(blank=True, null=True)
    order_status = models.CharField(
        max_length=30,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"], name="order_customer_created_idx"),
            models.Index(fields=["order_status", "-created_at"], name="order_status_created_idx"),
            models.Index(fields=["delivery_staff", "order_status"], name="order_delivery_status_idx"),
            models.Index(fields=["payment_status", "-created_at"], name="order_payment_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(subtotal__gte=0), name="order_subtotal_nonnegative"),
            models.CheckConstraint(condition=models.Q(discount__gte=0), name="order_discount_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(delivery_charge__gte=0),
                name="order_delivery_charge_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="order_total_nonnegative",
            ),
        ]

    def __str__(self):
        return self.order_number

    def get_absolute_url(self):
        return reverse("orders:order_detail", kwargs={"pk": self.pk})

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"MM{uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    vendor_product = models.ForeignKey(
        VendorProduct,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="order_items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    prescription_item = models.ForeignKey(
        "prescriptions.PrescriptionItem",
        on_delete=models.PROTECT,
        related_name="order_items",
        blank=True,
        null=True,
    )
    dispensed_batch = models.ForeignKey(
        "orders.InventoryBatch",
        on_delete=models.PROTECT,
        related_name="dispensed_order_items",
        blank=True,
        null=True,
    )
    product_name = models.CharField(max_length=180)
    seller_name = models.CharField(max_length=160)
    sku = models.CharField(max_length=60)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    class Meta:
        indexes = [
            models.Index(fields=["vendor", "order"], name="order_item_vendor_order_idx"),
            models.Index(fields=["product", "order"], name="order_item_product_order_idx"),
        ]


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=30, choices=Order.OrderStatus.choices)
    note = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="order_status_changes",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "order status histories"

    def __str__(self):
        return f"{self.order.order_number} - {self.get_status_display()}"


class Payment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    payment_method = models.CharField(max_length=20, choices=Order.PaymentMethod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Order.PaymentStatus.choices,
        default=Order.PaymentStatus.PENDING,
    )
    currency = models.CharField(max_length=3, default="INR")
    gateway_order_id = models.CharField(max_length=80, blank=True, null=True, unique=True)
    gateway_payment_id = models.CharField(max_length=80, blank=True, null=True, unique=True)
    gateway_signature = models.CharField(max_length=160, blank=True)
    gateway_status = models.CharField(max_length=30, blank=True)
    captured_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    failure_code = models.CharField(max_length=100, blank=True)
    failure_description = models.CharField(max_length=500, blank=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    last_gateway_check_at = models.DateTimeField(blank=True, null=True)
    gateway_metadata = models.JSONField(default=dict, blank=True)
    transaction_id = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for {self.order.order_number}"


class Refund(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    return_request = models.OneToOneField(
        "orders.ReturnRequest",
        on_delete=models.SET_NULL,
        related_name="refund",
        blank=True,
        null=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    gateway_refund_id = models.CharField(max_length=100, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="requested_refunds",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="refund_amount_positive")
        ]


class Warehouse(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=140)
    address = models.TextField()
    pincode = models.CharField(max_length=10, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class InventoryBatch(models.Model):
    vendor_product = models.ForeignKey(
        VendorProduct,
        on_delete=models.PROTECT,
        related_name="inventory_batches",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="inventory_batches",
    )
    batch_number = models.CharField(max_length=80)
    manufactured_on = models.DateField(blank=True, null=True)
    expires_on = models.DateField(blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    is_quarantined = models.BooleanField(default=False)
    quarantine_reason = models.CharField(max_length=255, blank=True)
    recall_reference = models.CharField(max_length=120, blank=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    supplier_name = models.CharField(max_length=180, blank=True)
    supplier_invoice_number = models.CharField(max_length=120, blank=True)
    dispensing_pharmacy = models.CharField(max_length=180, blank=True)
    storage_min_celsius = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    storage_max_celsius = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    excursion_status = models.CharField(max_length=20, default="normal", choices=[
        ("normal", "Normal"),
        ("excursion", "Temperature excursion"),
        ("investigating", "Under investigation"),
    ])
    temperature_log = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "inventory batches"
        constraints = [
            models.UniqueConstraint(
                fields=["vendor_product", "warehouse", "batch_number"],
                name="unique_offer_warehouse_batch",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__lte=models.F("quantity")),
                name="inventory_reserved_lte_quantity",
            ),
        ]
        indexes = [models.Index(fields=["expires_on", "quantity"], name="inventory_expiry_qty_idx")]

    def clean(self):
        super().clean()
        errors = {}
        if self.storage_min_celsius is not None and self.storage_max_celsius is not None:
            if self.storage_min_celsius > self.storage_max_celsius:
                errors["storage_max_celsius"] = "Maximum storage temperature must be at least the minimum."
        if self.manufactured_on and self.expires_on and self.expires_on <= self.manufactured_on:
            errors["expires_on"] = "Expiry must be after the manufacturing date."
        if errors:
            raise ValidationError(errors)

    @property
    def available_quantity(self):
        return max(0, self.quantity - self.reserved_quantity)

    def is_sellable(self, on_date=None, minimum_shelf_life_days=0):
        on_date = on_date or timezone.localdate()
        if self.is_quarantined or self.excursion_status != "normal" or self.available_quantity <= 0:
            return False
        if self.expires_on and self.expires_on <= on_date:
            return False
        if self.expires_on and minimum_shelf_life_days:
            if self.expires_on < on_date + timedelta(days=minimum_shelf_life_days):
                return False
        return True


class InventoryMovement(models.Model):
    class MovementType(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        RESERVATION = "reservation", "Reservation"
        RELEASE = "release", "Release"
        SALE = "sale", "Sale"
        RETURN = "return", "Return"
        ADJUSTMENT = "adjustment", "Adjustment"

    batch = models.ForeignKey(InventoryBatch, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.IntegerField()
    reference = models.CharField(max_length=100, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="inventory_movements",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)


class InventoryTemperatureLog(models.Model):
    batch = models.ForeignKey(InventoryBatch, on_delete=models.PROTECT, related_name="temperature_readings")
    temperature_celsius = models.DecimalField(max_digits=5, decimal_places=2)
    recorded_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=80, default="manual")
    is_excursion = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="inventory_temperature_logs",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-recorded_at"]

    def save(self, *args, **kwargs):
        lower = self.batch.storage_min_celsius
        upper = self.batch.storage_max_celsius
        outside_range = (lower is not None and self.temperature_celsius < lower) or (upper is not None and self.temperature_celsius > upper)
        if outside_range:
            self.is_excursion = True
        super().save(*args, **kwargs)
        if self.is_excursion:
            InventoryBatch.objects.filter(pk=self.batch_id).update(
                excursion_status="excursion",
                is_quarantined=True,
                quarantine_reason="Temperature excursion requires investigation.",
                updated_at=timezone.now(),
            )


class RecallNotice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active recall"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="recall_notices")
    batch = models.ForeignKey(InventoryBatch, on_delete=models.PROTECT, related_name="recall_notices", blank=True, null=True)
    reference = models.CharField(max_length=120)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="initiated_recalls")
    affected_customers_notified_at = models.DateTimeField(blank=True, null=True)
    reverse_pickup_required = models.BooleanField(default=False)
    regulatory_report_reference = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "reference"], name="unique_product_recall_reference"),
        ]


class DispensingRecord(models.Model):
    order_item = models.OneToOneField(OrderItem, on_delete=models.PROTECT, related_name="dispensing_record")
    prescription_item = models.ForeignKey("prescriptions.PrescriptionItem", on_delete=models.PROTECT, related_name="dispensing_records", blank=True, null=True)
    pharmacist = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="dispensed_order_items")
    pharmacy_license_number = models.CharField(max_length=120)
    batch = models.ForeignKey(InventoryBatch, on_delete=models.PROTECT, related_name="dispensing_records")
    quantity = models.PositiveIntegerField()
    substitution_made = models.BooleanField(default=False)
    substitution_details = models.TextField(blank=True)
    original_prescription_checked = models.BooleanField(default=False)
    patient_identity_checked = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    dispensed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-dispensed_at"]

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Dispensed quantity must be greater than zero."})
        if self.batch_id and self.order_item_id and self.batch.vendor_product.product_id != self.order_item.product_id:
            raise ValidationError({"batch": "The dispensing batch must belong to the ordered product."})
        if self.substitution_made and not self.substitution_details.strip():
            raise ValidationError({"substitution_details": "Describe the approved substitution."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        OrderItem.objects.filter(pk=self.order_item_id).update(dispensed_batch_id=self.batch_id)


class Shipment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        BOOKED = "booked", "Booked"
        IN_TRANSIT = "in_transit", "In transit"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        EXCEPTION = "exception", "Exception"
        RETURNED = "returned", "Returned"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipment")
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="shipments",
        blank=True,
        null=True,
    )
    courier_name = models.CharField(max_length=120, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    promised_at = models.DateTimeField(blank=True, null=True)
    shipped_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    delivery_otp_hash = models.CharField(max_length=128, blank=True)
    delivery_otp_issued_at = models.DateTimeField(blank=True, null=True)
    delivery_otp_verified_at = models.DateTimeField(blank=True, null=True)
    delivery_recipient_name = models.CharField(max_length=120, blank=True)
    delivery_proof = models.FileField(
        upload_to="delivery-proof/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def issue_delivery_otp(self):
        otp = f"{secrets.randbelow(1_000_000):06d}"
        self.delivery_otp_hash = make_password(otp)
        self.delivery_otp_issued_at = timezone.now()
        self.delivery_otp_verified_at = None
        self.save(update_fields=["delivery_otp_hash", "delivery_otp_issued_at", "delivery_otp_verified_at", "updated_at"])
        return otp

    def verify_delivery_otp(self, otp):
        if not otp or not self.delivery_otp_hash or not check_password(str(otp).strip(), self.delivery_otp_hash):
            return False
        self.delivery_otp_verified_at = timezone.now()
        self.save(update_fields=["delivery_otp_verified_at", "updated_at"])
        return True


class ShipmentEvent(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=30, choices=Shipment.Status.choices)
    location = models.CharField(max_length=160, blank=True)
    description = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["occurred_at"]


class PaymentEvent(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="events",
        blank=True,
        null=True,
    )
    event_id = models.CharField(max_length=120, unique=True)
    event_type = models.CharField(max_length=80)
    payload_hash = models.CharField(max_length=64, unique=True)
    gateway_order_id = models.CharField(max_length=80, blank=True)
    gateway_payment_id = models.CharField(max_length=80, blank=True)
    processed = models.BooleanField(default=False)
    processing_error = models.CharField(max_length=500, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["event_type", "-received_at"], name="payment_event_type_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.event_id}"


class OrderChargeBreakdown(models.Model):
    """Immutable-at-checkout money breakdown shown to the customer before payment."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="charge_breakdown")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    handling_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cold_chain_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "order charge breakdown"
        verbose_name_plural = "order charge breakdowns"

    def __str__(self):
        return f"Charges for {self.order.order_number}"


class PaymentReconciliation(models.Model):
    class Status(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        MATCHED = "matched", "Matched"
        EXCEPTION = "exception", "Exception"
        RESOLVED = "resolved", "Resolved"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="reconciliations")
    provider_reference = models.CharField(max_length=120, blank=True)
    provider_status = models.CharField(max_length=40, blank=True)
    gateway_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNMATCHED)
    exception_reason = models.CharField(max_length=255, blank=True)
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="payment_reconciliations")
    reconciled_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"], name="payment_reconcile_status_idx")]


class PaymentSettlement(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RECEIVED = "received", "Received"
        EXCEPTION = "exception", "Exception"

    provider = models.CharField(max_length=40, default="razorpay")
    settlement_reference = models.CharField(max_length=120, unique=True)
    settlement_date = models.DateField()
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Chargeback(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        EVIDENCE_SUBMITTED = "evidence_submitted", "Evidence submitted"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="chargebacks")
    provider_case_id = models.CharField(max_length=120, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN)
    evidence_note = models.TextField(blank=True)
    due_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class CreditNote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        VOID = "void", "Void"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="credit_notes")
    note_number = models.CharField(max_length=40, unique=True, editable=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="issued_credit_notes")
    issued_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.note_number:
            self.note_number = f"CN-{uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class CouponUsage(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="usages")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coupon_usages",
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="coupon_usages")
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["coupon", "user"],
                name="unique_coupon_usage_per_user",
            )
        ]

    def __str__(self):
        return f"{self.coupon.code} used by {self.user.username}"


class ReturnRequest(models.Model):
    class Reason(models.TextChoices):
        DAMAGED = "damaged", "Damaged or tampered"
        WRONG_ITEM = "wrong_item", "Wrong item delivered"
        EXPIRED = "expired", "Expired or near expiry"
        QUALITY = "quality", "Product-quality concern"
        MISSING = "missing", "Item missing"
        OTHER = "other", "Other eligible reason"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        PICKUP_SCHEDULED = "pickup_scheduled", "Pickup scheduled"
        RECEIVED = "received", "Received"
        REFUND_PENDING = "refund_pending", "Refund pending"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class InspectionDecision(models.TextChoices):
        PENDING = "pending", "Inspection pending"
        ACCEPTED = "accepted", "Accepted for refund"
        RESTOCKED = "restocked", "Restocked"
        QUARANTINED = "quarantined", "Quarantined"
        REJECTED = "rejected", "Rejected after inspection"

    order_item = models.ForeignKey(OrderItem, on_delete=models.PROTECT, related_name="return_requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="return_requests")
    reason = models.CharField(max_length=30, choices=Reason.choices)
    quantity = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    evidence = models.FileField(
        upload_to="returns/",
        storage=private_media_storage,
        validators=[validate_private_document],
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REQUESTED)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    pickup_scheduled_at = models.DateTimeField(blank=True, null=True)
    pickup_reference = models.CharField(max_length=120, blank=True)
    received_at = models.DateTimeField(blank=True, null=True)
    inspection_decision = models.CharField(
        max_length=20,
        choices=InspectionDecision.choices,
        default=InspectionDecision.PENDING,
    )
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="inspected_return_requests",
        blank=True,
        null=True,
    )
    inspected_at = models.DateTimeField(blank=True, null=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    resolution_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_return_requests",
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="return_quantity_positive"),
        ]

    def __str__(self):
        return f"Return #{self.pk} for {self.order_item.order.order_number}"
