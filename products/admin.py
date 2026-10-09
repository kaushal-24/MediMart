from django.contrib import admin

from .models import Brand, Category, Product, ProductImage, ProductSpecification


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
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
        "is_active",
        "is_featured",
    )
    search_fields = ("name", "sku", "manufacturer", "composition")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = (ProductImageInline, ProductSpecificationInline)
    actions = ("mark_active", "mark_inactive", "mark_featured")

    @admin.action(description="Mark selected products active")
    def mark_active(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Mark selected products inactive")
    def mark_inactive(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Mark selected products featured")
    def mark_featured(self, request, queryset):
        queryset.update(is_featured=True)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "alt_text", "is_primary", "created_at")
    list_filter = ("is_primary",)
    search_fields = ("product__name", "alt_text")


@admin.register(ProductSpecification)
class ProductSpecificationAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "value")
    search_fields = ("product__name", "name", "value")
