from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from core.validators import validate_public_image


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True, validators=[validate_public_image])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("products:category_detail", kwargs={"slug": self.slug})


class Brand(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    logo = models.ImageField(upload_to="brands/", blank=True, null=True, validators=[validate_public_image])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    class RegulationType(models.TextChoices):
        NONE = "none", "No special seller licence"
        DRUG_SALE = "drug_sale", "Drug sale licence"
        MEDICAL_DEVICE_SALE = "medical_device_sale", "Medical device sale registration"
        MEDICAL_DEVICE_MANUFACTURE = "medical_device_manufacture", "Medical device manufacturing licence"
        MEDICAL_DEVICE_IMPORT = "medical_device_import", "Medical device import licence"

    class ProductType(models.TextChoices):
        MEDICINE = "medicine", "Medicine"
        MEDICAL_EQUIPMENT = "medical_equipment", "Medical Equipment"
        SURGICAL_EQUIPMENT = "surgical_equipment", "Surgical Equipment"
        DIAGNOSTIC_EQUIPMENT = "diagnostic_equipment", "Diagnostic Equipment"
        HEALTHCARE_PRODUCT = "healthcare_product", "Healthcare Product"
        PERSONAL_CARE = "personal_care", "Personal Care"
        SUPPLEMENT = "supplement", "Supplement"
        BABY_CARE = "baby_care", "Baby Care"
        FITNESS_EQUIPMENT = "fitness_equipment", "Fitness Equipment"
        ORTHOPEDIC_PRODUCT = "orthopedic_product", "Orthopedic Product"
        FIRST_AID = "first_aid", "First Aid"
        LAB_EQUIPMENT = "lab_equipment", "Lab Equipment"

    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    sku = models.CharField(max_length=60, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
    )
    product_type = models.CharField(max_length=40, choices=ProductType.choices)
    image = models.ImageField(upload_to="products/", blank=True, null=True, validators=[validate_public_image])
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    requires_prescription = models.BooleanField(default=False)
    requires_business_license = models.BooleanField(default=False)
    required_license_type = models.CharField(
        max_length=40,
        choices=RegulationType.choices,
        default=RegulationType.NONE,
    )
    regulatory_classification = models.CharField(max_length=80, blank=True)
    regulatory_notes = models.TextField(blank=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    composition = models.CharField(max_length=255, blank=True)
    pack_size = models.CharField(max_length=80, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    weight = models.CharField(max_length=80, blank=True)
    dimensions = models.CharField(max_length=120, blank=True)
    seo_title = models.CharField(max_length=180, blank=True)
    seo_description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "is_featured"], name="product_active_featured_idx"),
            models.Index(fields=["category", "is_active"], name="product_category_active_idx"),
            models.Index(fields=["product_type", "is_active"], name="product_type_active_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(mrp__gte=0),
                name="product_mrp_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(selling_price__gte=0),
                name="product_selling_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(selling_price__lte=models.F("mrp")),
                name="product_selling_price_lte_mrp",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("products:product_detail", kwargs={"slug": self.slug})

    @property
    def discount_percentage(self):
        if not self.mrp or self.mrp <= self.selling_price:
            return 0
        discount = ((self.mrp - self.selling_price) / self.mrp) * Decimal("100")
        return int(discount)

    @property
    def stock_status(self):
        if self.stock_quantity == 0:
            return "Out of Stock"
        if self.stock_quantity <= 5:
            return "Low Stock"
        return "In Stock"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/gallery/", validators=[validate_public_image])
    alt_text = models.CharField(max_length=150, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "id"]

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductSpecification(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="specifications")
    name = models.CharField(max_length=120)
    value = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.product.name}: {self.name}"
