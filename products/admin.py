from django.contrib import admin
from django.utils import timezone

from .models import (
    Brand,
    Category,
    ClinicalInteraction,
    PriceAlert,
    Product,
    ProductClinicalProfile,
    ProductImage,
    ProductQuestion,
    ProductSpecification,
    ProductSubstitute,
    ProductVariant,
    StockAlert,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


class ProductSubstituteInline(admin.TabularInline):
    model = ProductSubstitute
    fk_name = "product"
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active", "updated_at")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "brand",
        "product_type",
        "selling_price",
        "stock_quantity",
        "requires_prescription",
        "requires_business_license",
        "safety_classification",
        "regulatory_schedule",
        "requires_pharmacist_review",
        "recall_status",
        "cold_chain_required",
        "is_active",
        "is_featured",
    )
    list_filter = (
        "product_type",
        "category",
        "brand",
        "requires_prescription",
        "requires_business_license",
        "required_license_type",
        "safety_classification",
        "regulatory_schedule",
        "requires_pharmacist_review",
        "recall_status",
        "cold_chain_required",
        "is_active",
        "is_featured",
    )
    search_fields = ("name", "sku", "barcode", "manufacturer", "composition", "recall_reference")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = (ProductImageInline, ProductSpecificationInline, ProductVariantInline, ProductSubstituteInline)
    actions = ("mark_active", "mark_inactive", "mark_featured", "quarantine_products", "clear_product_recall")

    @admin.action(description="Mark selected products active")
    def mark_active(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Mark selected products inactive")
    def mark_inactive(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Mark selected products featured")
    def mark_featured(self, request, queryset):
        queryset.update(is_featured=True)

    @admin.action(description="Quarantine selected products")
    def quarantine_products(self, request, queryset):
        queryset.update(recall_status=Product.RecallStatus.QUARANTINED, is_active=False)

    @admin.action(description="Clear recall/quarantine from selected products")
    def clear_product_recall(self, request, queryset):
        queryset.update(recall_status=Product.RecallStatus.CLEAR, recall_reference="", recall_reason="")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "alt_text", "is_primary", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__name", "alt_text")


@admin.register(ProductSpecification)
class ProductSpecificationAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "value")
    search_fields = ("product__name", "name", "value")


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "sku", "pack_size", "strength", "selling_price", "stock_quantity", "is_approved", "is_active")
    list_filter = ("is_approved", "is_active", "product__product_type")
    search_fields = ("product__name", "sku", "pack_size", "strength")
    actions = ("approve_variants", "deactivate_variants")

    @admin.action(description="Approve selected product variants")
    def approve_variants(self, request, queryset):
        queryset.update(is_approved=True)

    @admin.action(description="Deactivate selected product variants")
    def deactivate_variants(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(ProductSubstitute)
class ProductSubstituteAdmin(admin.ModelAdmin):
    list_display = ("product", "substitute", "status", "approved_by", "approved_at")
    list_filter = ("status",)
    search_fields = ("product__name", "substitute__name", "rationale")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProductQuestion)
class ProductQuestionAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "status", "answered_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("product__name", "user__username", "question", "answer")
    readonly_fields = ("created_at", "updated_at")
    actions = ("mark_answered", "reject_questions")

    @admin.action(description="Mark selected questions answered")
    def mark_answered(self, request, queryset):
        queryset.update(status=ProductQuestion.Status.ANSWERED, answered_by=request.user, answered_at=timezone.now())

    @admin.action(description="Reject selected questions")
    def reject_questions(self, request, queryset):
        queryset.update(status=ProductQuestion.Status.REJECTED, answered_by=request.user, answered_at=timezone.now())


@admin.register(ProductClinicalProfile)
class ProductClinicalProfileAdmin(admin.ModelAdmin):
    list_display = ("product", "therapeutic_class", "review_status", "reviewed_by", "reviewed_at")
    list_filter = ("review_status", "severity_level", "therapeutic_class")
    search_fields = ("product__name", "active_ingredient", "therapeutic_class", "uses", "dosage_information")
    readonly_fields = ("last_updated_at",)
    actions = ("publish_profiles", "archive_profiles")

    @admin.action(description="Publish selected reviewed clinical profiles")
    def publish_profiles(self, request, queryset):
        queryset.update(review_status=ProductClinicalProfile.ReviewStatus.PUBLISHED, reviewed_by=request.user)

    @admin.action(description="Archive selected clinical profiles")
    def archive_profiles(self, request, queryset):
        queryset.update(review_status=ProductClinicalProfile.ReviewStatus.ARCHIVED)


@admin.register(ClinicalInteraction)
class ClinicalInteractionAdmin(admin.ModelAdmin):
    list_display = ("product", "interaction_type", "trigger", "severity", "is_published", "reviewed_by")
    list_filter = ("interaction_type", "severity", "is_published")
    search_fields = ("product__name", "trigger", "guidance", "source_reference")
    actions = ("publish_interactions", "unpublish_interactions")

    @admin.action(description="Publish selected clinical interactions")
    def publish_interactions(self, request, queryset):
        queryset.update(is_published=True, reviewed_by=request.user)

    @admin.action(description="Unpublish selected clinical interactions")
    def unpublish_interactions(self, request, queryset):
        queryset.update(is_published=False)


@admin.register(StockAlert)
class StockAlertAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "is_active", "notified_at", "created_at")
    list_filter = ("is_active", "notified_at")
    search_fields = ("user__username", "user__email", "product__name", "product__sku")
    readonly_fields = ("created_at", "notified_at")


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "target_price", "is_active", "notified_at", "created_at")
    list_filter = ("is_active", "notified_at", "created_at")
    search_fields = ("user__username", "user__email", "product__name", "product__sku")
    readonly_fields = ("created_at", "updated_at", "notified_at")
