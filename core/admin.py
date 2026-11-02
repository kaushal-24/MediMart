from django.contrib import admin

from .models import AuditEvent, CheckoutSettings


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target_type", "target_id", "ip_address")
    list_filter = ("action", "target_type", "created_at")
    search_fields = ("actor__username", "action", "target_type", "target_id", "summary")
    readonly_fields = (
        "actor",
        "action",
        "target_type",
        "target_id",
        "summary",
        "metadata",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckoutSettings)
class CheckoutSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "delivery_fee",
        "free_delivery",
        "tax_rate_percent",
        "handling_fee",
        "platform_fee",
        "cold_chain_fee",
        "cod_max_order_value",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at", "updated_by")

    def has_add_permission(self, request):
        return not CheckoutSettings.objects.exists()
