from decimal import Decimal

from django.conf import settings
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
    class SafetyClassification(models.TextChoices):
        OTC = "otc", "Over the counter"
        PRESCRIPTION = "prescription", "Prescription medicine"
        CONTROLLED = "controlled", "Controlled / restricted"
        SCHEDULE_X = "schedule_x", "Schedule X - not for online sale"
        PROHIBITED = "prohibited", "Prohibited for online sale"

    class RecallStatus(models.TextChoices):
        CLEAR = "clear", "Clear for sale"
        QUARANTINED = "quarantined", "Quarantined"
        RECALLED = "recalled", "Recalled"

    class RegulationType(models.TextChoices):
        NONE = "none", "No special seller licence"
        DRUG_SALE = "drug_sale", "Drug sale licence"
        MEDICAL_DEVICE_SALE = "medical_device_sale", "Medical device sale registration"
        MEDICAL_DEVICE_MANUFACTURE = "medical_device_manufacture", "Medical device manufacturing licence"
        MEDICAL_DEVICE_IMPORT = "medical_device_import", "Medical device import licence"

    class RegulatorySchedule(models.TextChoices):
        NONE = "none", "No schedule"
        H = "schedule_h", "Schedule H"
        H1 = "schedule_h1", "Schedule H1"
        NDPS = "ndps", "NDPS / controlled substance"
        HABIT_FORMING = "habit_forming", "Habit-forming"
        STATE_RESTRICTED = "state_restricted", "State-specific restriction"

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
    regulatory_schedule = models.CharField(max_length=20, choices=RegulatorySchedule.choices, default=RegulatorySchedule.NONE)
    state_restrictions = models.JSONField(default=list, blank=True, help_text="States or rules requiring manual compliance review.")
    requires_pharmacist_review = models.BooleanField(default=False)
    safety_classification = models.CharField(
        max_length=20,
        choices=SafetyClassification.choices,
        default=SafetyClassification.OTC,
        help_text="Controls online sale and the safeguards shown at checkout.",
    )
    recall_status = models.CharField(
        max_length=20,
        choices=RecallStatus.choices,
        default=RecallStatus.CLEAR,
    )
    recall_reference = models.CharField(max_length=120, blank=True)
    recall_reason = models.TextField(blank=True)
    quantity_limit_per_order = models.PositiveIntegerField(default=0)
    minimum_shelf_life_days = models.PositiveIntegerField(default=0)
    cold_chain_required = models.BooleanField(default=False)
    barcode = models.CharField(max_length=80, blank=True, db_index=True)
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
        derived_update_fields = kwargs.get("update_fields")
        if self.safety_classification in {
            self.SafetyClassification.PRESCRIPTION,
            self.SafetyClassification.CONTROLLED,
        }:
            self.requires_prescription = True
            if derived_update_fields is not None:
                derived_update_fields = set(derived_update_fields) | {"requires_prescription"}
        if self.regulatory_schedule in {
            self.RegulatorySchedule.H,
            self.RegulatorySchedule.H1,
            self.RegulatorySchedule.NDPS,
            self.RegulatorySchedule.HABIT_FORMING,
            self.RegulatorySchedule.STATE_RESTRICTED,
        }:
            self.requires_prescription = True
            self.requires_pharmacist_review = True
            if derived_update_fields is not None:
                derived_update_fields = set(derived_update_fields) | {"requires_prescription", "requires_pharmacist_review"}
        if self.safety_classification in {
            self.SafetyClassification.SCHEDULE_X,
            self.SafetyClassification.PROHIBITED,
        }:
            self.is_active = False
            if derived_update_fields is not None:
                derived_update_fields = set(derived_update_fields) | {"is_active"}
        if derived_update_fields is not None:
            kwargs["update_fields"] = derived_update_fields
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("products:product_detail", kwargs={"slug": self.slug})

    def is_allowed_in_state(self, state):
        """Evaluate configured state restrictions without assuming one JSON shape."""
        state = str(state or "").strip().casefold()
        if not state or not self.state_restrictions:
            return True
        restrictions = self.state_restrictions
        if isinstance(restrictions, dict):
            allowed_states = {str(value).strip().casefold() for value in restrictions.get("allowed_states", [])}
            blocked_states = {str(value).strip().casefold() for value in restrictions.get("blocked_states", [])}
            if allowed_states:
                return state in allowed_states
            return state not in blocked_states
        blocked_states = {str(value).strip().casefold() for value in restrictions}
        return state not in blocked_states

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


class StockAlert(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stock_alerts",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_alerts",
    )
    is_active = models.BooleanField(default=True)
    notified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_user_product_stock_alert",
            )
        ]
        indexes = [
            models.Index(
                fields=["product", "is_active", "notified_at"],
                name="stock_alert_product_idx",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.product.name}"


class PriceAlert(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="price_alerts")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_alerts")
    target_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    notified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_user_product_price_alert"),
            models.CheckConstraint(condition=models.Q(target_price__gte=0), name="price_alert_target_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["product", "is_active", "target_price"], name="price_alert_product_idx"),
        ]

    def __str__(self):
        return f"{self.user} - {self.product.name} at ₹{self.target_price}"


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


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=80, unique=True)
    pack_size = models.CharField(max_length=80, blank=True)
    strength = models.CharField(max_length=120, blank=True)
    dosage_form = models.CharField(max_length=100, blank=True)
    flavour = models.CharField(max_length=80, blank=True)
    form = models.CharField(max_length=80, blank=True)
    colour = models.CharField(max_length=80, blank=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "pack_size", "strength", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(mrp__gte=0), name="variant_mrp_nonnegative"),
            models.CheckConstraint(condition=models.Q(selling_price__gte=0), name="variant_price_nonnegative"),
            models.CheckConstraint(condition=models.Q(selling_price__lte=models.F("mrp")), name="variant_price_lte_mrp"),
        ]
        indexes = [
            models.Index(fields=["product", "is_approved", "is_active"], name="variant_product_status_idx"),
        ]

    def __str__(self):
        label = " / ".join(value for value in [self.pack_size, self.strength, self.dosage_form, self.flavour] if value)
        return f"{self.product.name} - {label or self.sku}"


class ProductSubstitute(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending pharmacist review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="substitute_links")
    substitute = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="substitute_for")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rationale = models.TextField(blank=True, help_text="Clinical or catalogue rationale for pharmacist review.")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="approved_product_substitutes", blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["substitute__name"]
        constraints = [models.UniqueConstraint(fields=["product", "substitute"], name="unique_product_substitute")]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.product_id and self.product_id == self.substitute_id:
            raise ValidationError("A product cannot be its own substitute.")

    def __str__(self):
        return f"{self.product.name} -> {self.substitute.name}"


class ProductQuestion(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending moderation"
        ANSWERED = "answered", "Answered"
        REJECTED = "rejected", "Rejected"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="questions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_questions")
    question = models.TextField()
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="answered_product_questions", blank=True, null=True)
    answered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["product", "status", "created_at"], name="product_question_status_idx")]

    def __str__(self):
        return f"Question about {self.product.name}: {self.question[:60]}"


class ProductSpecification(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="specifications")
    name = models.CharField(max_length=120)
    value = models.CharField(max_length=255)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.product.name}: {self.name}"


class ProductClinicalProfile(models.Model):
    class ReviewStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        UNDER_REVIEW = "under_review", "Under review"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class SeverityLevel(models.TextChoices):
        ROUTINE = "routine", "Routine information"
        IMPORTANT = "important", "Important precautions"
        URGENT = "urgent", "Urgent medical attention"

    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="clinical_profile")
    active_ingredient = models.CharField(max_length=255, blank=True)
    strength = models.CharField(max_length=120, blank=True)
    dosage_form = models.CharField(max_length=100, blank=True)
    route = models.CharField(max_length=100, blank=True)
    therapeutic_class = models.CharField(max_length=180, blank=True)
    chemical_class = models.CharField(max_length=180, blank=True)
    action_class = models.CharField(max_length=180, blank=True)
    habit_forming = models.BooleanField(default=False)
    uses = models.TextField(blank=True)
    benefits = models.TextField(blank=True)
    dosage_information = models.TextField(
        blank=True,
        help_text="Clinically reviewed general dosage information. Never replaces a prescriber's directions.",
    )
    onset_information = models.CharField(max_length=255, blank=True)
    duration_information = models.CharField(max_length=255, blank=True)
    quick_tips = models.TextField(blank=True)
    severity_level = models.CharField(
        max_length=20,
        choices=SeverityLevel.choices,
        blank=True,
        help_text="Reviewed attention level for the information shown on the product page.",
    )
    side_effects = models.TextField(blank=True)
    usage = models.TextField(blank=True)
    how_it_works = models.TextField(blank=True)
    safety_advice = models.TextField(blank=True)
    pregnancy_advice = models.TextField(blank=True)
    breastfeeding_advice = models.TextField(blank=True)
    alcohol_advice = models.TextField(blank=True)
    driving_advice = models.TextField(blank=True)
    kidney_advice = models.TextField(blank=True)
    liver_advice = models.TextField(blank=True)
    interaction_summary = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    allergy_warnings = models.TextField(blank=True)
    missed_dose = models.TextField(blank=True)
    overdose = models.TextField(blank=True)
    child_senior_advice = models.TextField(blank=True)
    storage_instructions = models.CharField(max_length=255, blank=True)
    marketer = models.CharField(max_length=180, blank=True)
    country_of_origin = models.CharField(max_length=100, blank=True)
    manufacturing_address = models.TextField(blank=True)
    manufacturing_license = models.CharField(max_length=160, blank=True)
    gst_hsn_code = models.CharField(max_length=40, blank=True)
    nppa_status = models.CharField(max_length=120, blank=True)
    content_sources = models.TextField(blank=True)
    source_url = models.URLField(blank=True)
    last_reviewed_at = models.DateTimeField(blank=True, null=True)
    review_due_at = models.DateTimeField(blank=True, null=True)
    correction_note = models.TextField(blank=True)
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_clinical_profiles",
        blank=True,
        null=True,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "product clinical profile"
        verbose_name_plural = "product clinical profiles"

    def __str__(self):
        return f"Clinical profile: {self.product.name}"


class ClinicalInteraction(models.Model):
    class InteractionType(models.TextChoices):
        DRUG_DRUG = "drug_drug", "Drug-drug"
        DRUG_FOOD = "drug_food", "Drug-food"
        DRUG_ALCOHOL = "drug_alcohol", "Drug-alcohol"
        PREGNANCY = "pregnancy", "Pregnancy"
        KIDNEY = "kidney", "Kidney"
        LIVER = "liver", "Liver"
        ALLERGY = "allergy", "Allergy"
        CONDITION = "condition", "Condition"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="clinical_interactions")
    related_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="related_interactions", blank=True, null=True)
    trigger = models.CharField(max_length=180)
    interaction_type = models.CharField(max_length=20, choices=InteractionType.choices)
    severity = models.CharField(max_length=20, default="important")
    guidance = models.TextField()
    source_reference = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="reviewed_clinical_interactions")
    reviewed_at = models.DateTimeField(blank=True, null=True)
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name", "interaction_type", "trigger"]
        indexes = [models.Index(fields=["product", "is_published"], name="clin_interaction_prod_idx")]


class SearchQuery(models.Model):
    """Privacy-conscious search analytics used for zero-result and catalogue improvements."""

    query = models.CharField(max_length=180, db_index=True)
    source = models.CharField(max_length=30, default="catalog")
    result_count = models.PositiveIntegerField(default=0)
    lab_result_count = models.PositiveIntegerField(default=0)
    zero_result = models.BooleanField(default=False, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="search_queries")
    session_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "zero_result", "-created_at"], name="search_query_metrics_idx"),
            models.Index(fields=["query", "-created_at"], name="search_query_recent_idx"),
        ]

    def __str__(self):
        return self.query
