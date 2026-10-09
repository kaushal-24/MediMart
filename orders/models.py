from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address
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
        DUMMY_ONLINE = "dummy_online", "Legacy Demo Online Payment"

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
    stock_reserved_until = models.DateTimeField(blank=True, null=True)
    inventory_released_at = models.DateTimeField(blank=True, null=True)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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
