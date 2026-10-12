from django.contrib import admin

from .models import (
    Coupon,
    CouponUsage,
    DispensingRecord,
    InventoryBatch,
    InventoryMovement,
    InventoryTemperatureLog,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PaymentEvent,
    OrderChargeBreakdown,
    PaymentReconciliation,
    PaymentSettlement,
    Chargeback,
    CreditNote,
    Refund,
    RecallNotice,
    ReturnRequest,
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


@admin.register(OrderChargeBreakdown)
class OrderChargeBreakdownAdmin(admin.ModelAdmin):
    list_display = ("order", "subtotal", "discount", "tax_amount", "handling_charge", "platform_fee", "delivery_charge", "cold_chain_charge", "total_amount")
    search_fields = ("order__order_number", "order__customer__username")
    readonly_fields = ("created_at",)


@admin.register(PaymentReconciliation)
class PaymentReconciliationAdmin(admin.ModelAdmin):
    list_display = ("payment", "provider_reference", "gateway_amount", "expected_amount", "status", "reconciled_at")
    list_filter = ("status", "provider_status", "created_at")
    search_fields = ("payment__order__order_number", "provider_reference", "exception_reason")


@admin.register(PaymentSettlement)
class PaymentSettlementAdmin(admin.ModelAdmin):
    list_display = ("settlement_reference", "provider", "settlement_date", "gross_amount", "net_amount", "status")
    list_filter = ("provider", "status", "settlement_date")
    search_fields = ("settlement_reference", "notes")


@admin.register(Chargeback)
class ChargebackAdmin(admin.ModelAdmin):
    list_display = ("provider_case_id", "payment", "amount", "status", "due_at", "resolved_at")
    list_filter = ("status", "due_at")
    search_fields = ("provider_case_id", "payment__order__order_number", "reason")


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("note_number", "order", "amount", "reason", "status", "issued_at")
    list_filter = ("status", "issued_at")
    search_fields = ("note_number", "order__order_number", "reason")
    readonly_fields = ("note_number", "created_at")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("payment", "return_request", "amount", "status", "gateway_refund_id", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("payment__order__order_number", "gateway_refund_id", "reason")


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("order_item", "user", "reason", "quantity", "status", "inspection_decision", "refund_amount", "requested_at")
    list_filter = ("reason", "status", "requested_at")
    search_fields = ("order_item__order__order_number", "user__username", "description")
    readonly_fields = ("requested_at", "updated_at", "received_at")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "pincode", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "pincode", "address")


@admin.register(InventoryBatch)
class InventoryBatchAdmin(admin.ModelAdmin):
    list_display = (
        "vendor_product",
        "warehouse",
        "batch_number",
        "quantity",
        "reserved_quantity",
        "expires_on",
        "is_quarantined",
        "recall_reference",
    )
    list_filter = ("warehouse", "expires_on", "is_quarantined")
    search_fields = (
        "batch_number",
        "recall_reference",
        "vendor_product__product__name",
        "vendor_product__vendor__business_name",
    )
    actions = ("quarantine_batches", "release_batches")

    @admin.action(description="Quarantine selected inventory batches")
    def quarantine_batches(self, request, queryset):
        queryset.update(is_quarantined=True, quarantine_reason="Manual safety hold")

    @admin.action(description="Release selected inventory batches")
    def release_batches(self, request, queryset):
        queryset.update(is_quarantined=False, quarantine_reason="")


@admin.register(InventoryTemperatureLog)
class InventoryTemperatureLogAdmin(admin.ModelAdmin):
    list_display = ("batch", "temperature_celsius", "recorded_at", "source", "is_excursion", "recorded_by")
    list_filter = ("is_excursion", "source", "recorded_at")
    search_fields = ("batch__batch_number", "batch__vendor_product__product__name", "note")


@admin.register(RecallNotice)
class RecallNoticeAdmin(admin.ModelAdmin):
    list_display = ("reference", "product", "batch", "status", "reverse_pickup_required", "affected_customers_notified_at")
    list_filter = ("status", "reverse_pickup_required", "created_at")
    search_fields = ("reference", "product__name", "reason", "regulatory_report_reference")
    readonly_fields = ("affected_customers_notified_at", "created_at", "updated_at")
    actions = ("activate_recalls", "complete_recalls", "cancel_recalls")

    @admin.action(description="Activate recalls, quarantine stock, and notify customers")
    def activate_recalls(self, request, queryset):
        from .services import activate_recall_notice
        count = 0
        for recall in queryset:
            activate_recall_notice(recall, actor=request.user)
            count += 1
        self.message_user(request, f"Activated {count} recall(s).")

    @admin.action(description="Complete selected recalls")
    def complete_recalls(self, request, queryset):
        queryset.update(status=RecallNotice.Status.COMPLETED)

    @admin.action(description="Cancel selected recalls")
    def cancel_recalls(self, request, queryset):
        queryset.update(status=RecallNotice.Status.CANCELLED)


@admin.register(DispensingRecord)
class DispensingRecordAdmin(admin.ModelAdmin):
    list_display = ("order_item", "pharmacist", "pharmacy_license_number", "batch", "quantity", "dispensed_at")
    list_filter = ("substitution_made", "original_prescription_checked", "patient_identity_checked", "dispensed_at")
    search_fields = ("order_item__order__order_number", "pharmacist__username", "pharmacy_license_number", "batch__batch_number")
    readonly_fields = ("dispensed_at",)


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
    list_display = ("order", "courier_name", "tracking_number", "status", "delivery_recipient_name", "delivery_otp_verified_at", "promised_at")
    list_filter = ("status", "courier_name")
    search_fields = ("order__order_number", "tracking_number")
    readonly_fields = ("delivery_otp_hash", "delivery_otp_issued_at", "delivery_otp_verified_at")
    inlines = (ShipmentEventInline,)
