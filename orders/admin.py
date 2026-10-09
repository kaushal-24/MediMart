from django.contrib import admin

from .models import (
    Coupon,
    CouponUsage,
    InventoryBatch,
    InventoryMovement,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PaymentEvent,
    Refund,
    Shipment,
    ShipmentEvent,
    Warehouse,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "seller_name", "sku", "quantity", "unit_price", "total_price")


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer",
        "total_amount",
        "payment_method",
        "payment_status",
        "order_status",
        "delivery_staff",
        "created_at",
    )
    list_filter = ("payment_method", "payment_status", "order_status", "delivery_staff", "created_at")
    search_fields = (
        "order_number",
        "customer__username",
        "customer__email",
        "delivery_staff__username",
    )
    readonly_fields = ("order_number", "created_at", "updated_at")
    inlines = (OrderItemInline, OrderStatusHistoryInline)
    actions = ("mark_confirmed", "mark_shipped", "mark_delivered")

    @admin.action(description="Mark selected orders confirmed")
    def mark_confirmed(self, request, queryset):
        queryset.update(order_status=Order.OrderStatus.CONFIRMED)

    @admin.action(description="Mark selected orders shipped")
    def mark_shipped(self, request, queryset):
        queryset.update(order_status=Order.OrderStatus.SHIPPED)

    @admin.action(description="Mark selected orders delivered")
    def mark_delivered(self, request, queryset):
        queryset.update(order_status=Order.OrderStatus.DELIVERED)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "seller_name", "quantity", "total_price")
    search_fields = ("order__order_number", "product_name", "seller_name", "sku")


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "note", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "note")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "payment_method", "amount", "status", "transaction_id", "created_at")
    list_filter = ("payment_method", "status", "created_at")
    search_fields = ("order__order_number", "transaction_id")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "discount_value", "minimum_order", "usage_limit", "is_active")
    list_filter = ("discount_type", "is_active", "start_date", "end_date")
    search_fields = ("code",)


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "used_at")
    search_fields = ("coupon__code", "user__username", "order__order_number")


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "payment", "processed", "received_at")
    list_filter = ("event_type", "processed", "received_at")
    search_fields = ("event_id", "gateway_order_id", "gateway_payment_id", "payment__order__order_number")
    readonly_fields = ("event_id", "event_type", "payment", "payload_hash", "payload", "received_at", "processed_at")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("payment", "amount", "status", "gateway_refund_id", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("payment__order__order_number", "gateway_refund_id", "reason")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "pincode", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "pincode", "address")


@admin.register(InventoryBatch)
class InventoryBatchAdmin(admin.ModelAdmin):
    list_display = ("vendor_product", "warehouse", "batch_number", "quantity", "reserved_quantity", "expires_on")
    list_filter = ("warehouse", "expires_on")
    search_fields = ("batch_number", "vendor_product__product__name", "vendor_product__vendor__business_name")


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ("batch", "movement_type", "quantity", "reference", "actor", "created_at")
    list_filter = ("movement_type", "created_at")
    search_fields = ("reference", "batch__batch_number")
    readonly_fields = ("created_at",)


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "courier_name", "tracking_number", "status", "promised_at")
    list_filter = ("status", "courier_name")
    search_fields = ("order__order_number", "tracking_number")
    inlines = (ShipmentEventInline,)
