from django.contrib import admin, messages

from .models import BusinessLicense, Vendor, VendorProduct


class BusinessLicenseInline(admin.TabularInline):
    model = BusinessLicense
    extra = 0
    fields = ("license_type", "license_number", "form_number", "status", "valid_until")
    readonly_fields = ("status",)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "owner_name",
        "business_type",
        "phone",
        "is_approved",
        "is_active",
    )
    list_filter = ("business_type", "is_approved", "is_active")
    search_fields = ("business_name", "owner_name", "email", "phone", "license_number")
    readonly_fields = ("created_at", "updated_at")
    actions = ("approve_vendors", "deactivate_vendors")
    inlines = (BusinessLicenseInline,)

    @admin.action(description="Approve selected vendors")
    def approve_vendors(self, request, queryset):
        approved = 0
        for vendor in queryset:
            if vendor.requires_regulatory_license and not vendor.has_verified_license:
                continue
            vendor.is_approved = True
            vendor.is_active = True
            vendor.save(update_fields=["is_approved", "is_active", "updated_at"])
            approved += 1
        self.message_user(
            request,
            f"Approved {approved} seller(s). Records without a current verified licence were skipped.",
            messages.SUCCESS if approved else messages.WARNING,
        )

    @admin.action(description="Deactivate selected vendors")
    def deactivate_vendors(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(BusinessLicense)
class BusinessLicenseAdmin(admin.ModelAdmin):
    list_display = (
        "license_number",
        "vendor",
        "license_type",
        "status",
        "verification_source",
        "valid_until",
        "reviewed_by",
    )
    list_filter = ("status", "license_type", "verification_source", "state")
    search_fields = ("license_number", "legal_name", "vendor__business_name")
    readonly_fields = ("registry_payload", "registry_checked_at", "created_at", "updated_at")


@admin.register(VendorProduct)
class VendorProductAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "vendor",
        "price",
        "stock_quantity",
        "delivery_time",
        "is_approved",
        "is_active",
    )
    list_filter = ("is_approved", "is_active", "vendor", "product__product_type")
    search_fields = ("product__name", "vendor__business_name", "offer_text")
    readonly_fields = ("created_at", "updated_at")
    actions = ("approve_offers", "mark_offers_inactive")

    @admin.action(description="Approve selected vendor offers")
    def approve_offers(self, request, queryset):
        approved = 0
        for offer in queryset.select_related("product", "vendor"):
            product = offer.product
            permitted = not product.requires_business_license or any(
                item.is_compatible_with(product.required_license_type)
                for item in offer.vendor.licenses.filter(status=BusinessLicense.Status.VERIFIED)
            )
            if not permitted:
                continue
            offer.is_approved = True
            offer.is_active = True
            offer.save(update_fields=["is_approved", "is_active", "updated_at"])
            approved += 1
        self.message_user(
            request,
            f"Approved {approved} offer(s). Offers missing compatible licences were skipped.",
            messages.SUCCESS if approved else messages.WARNING,
        )

    @admin.action(description="Mark selected offers inactive")
    def mark_offers_inactive(self, request, queryset):
        queryset.update(is_active=False)
