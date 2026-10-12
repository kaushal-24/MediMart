from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from accounts.forms import BootstrapFormMixin
from accounts.models import UserProfile
from extras.models import (
    BlogCategory,
    BlogPost,
    DoctorProfile,
    Notification,
    PharmacistProfile,
    QualityComplaint,
)
from healthcare.models import Consultation, LabBooking, LabCollectionSlot, LabPartner, LabTest
from orders.models import (
    Coupon,
    DispensingRecord,
    InventoryBatch,
    InventoryTemperatureLog,
    Order,
    Payment,
    RecallNotice,
    Refund,
    ReturnRequest,
    Shipment,
    Warehouse,
)
from products.models import Brand, Category, Product
from vendors.models import BusinessLicense, Vendor, VendorProduct


User = get_user_model()


class UserManagementForm(BootstrapFormMixin, forms.ModelForm):
    role = forms.ChoiceField(choices=UserProfile.Role.choices)
    password1 = forms.CharField(label="Password", required=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", required=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, "profile", None)
        if profile:
            self.fields["role"].initial = profile.role
        if self.instance.pk:
            # Usernames are account identifiers; administrators may update
            # profile details and passwords without silently renaming them.
            self.fields["username"].required = False
            self.fields["username"].disabled = True
        if not getattr(self.actor, "is_superuser", False):
            self.fields["role"].choices = [
                choice for choice in self.fields["role"].choices
                if choice[0] != UserProfile.Role.ADMIN
            ]
        self.apply_bootstrap_classes()

    def clean_role(self):
        role = self.cleaned_data["role"]
        current_role = getattr(getattr(self.instance, "profile", None), "role", None)
        if role == UserProfile.Role.ADMIN and not getattr(self.actor, "is_superuser", False):
            raise forms.ValidationError("Only a superuser can assign the administrator role.")
        if self.instance.pk and self.actor and self.instance.pk == self.actor.pk and role != current_role:
            raise forms.ValidationError("You cannot change your own role.")
        if current_role == UserProfile.Role.ADMIN and role != current_role and not getattr(self.actor, "is_superuser", False):
            raise forms.ValidationError("Only a superuser can change an administrator role.")
        return role

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if not self.instance.pk and not password1:
            self.add_error("password1", "A password is required for a new account.")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "Passwords do not match.")
            elif len(password1 or "") < 8:
                self.add_error("password1", "Use at least 8 characters.")
        return cleaned

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data["role"]
            profile.save(update_fields=["role"])
            if self.cleaned_data.get("password1"):
                user.set_password(self.cleaned_data["password1"])
                user.save(update_fields=["password"])
        return user


class ProductManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "category",
            "brand",
            "product_type",
            "short_description",
            "description",
            "image",
            "mrp",
            "selling_price",
            "stock_quantity",
            "requires_prescription",
            "requires_business_license",
            "required_license_type",
            "regulatory_classification",
            "regulatory_notes",
            "regulatory_schedule",
            "state_restrictions",
            "requires_pharmacist_review",
            "manufacturer",
            "composition",
            "pack_size",
            "is_active",
            "is_featured",
        ]
        widgets = {
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 6}),
            "regulatory_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("requires_business_license") and not cleaned.get("required_license_type"):
            self.add_error(
                "required_license_type",
                "Choose the licence category required for this regulated product.",
            )
        if cleaned.get("selling_price") is not None and cleaned.get("mrp") is not None:
            if cleaned["selling_price"] > cleaned["mrp"]:
                self.add_error("selling_price", "Selling price cannot exceed MRP.")
        return cleaned


class CategoryManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "description", "image", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class BrandManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Brand
        fields = ["name", "logo", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class CouponManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code",
            "discount_type",
            "discount_value",
            "minimum_order",
            "maximum_discount",
            "start_date",
            "end_date",
            "usage_limit",
            "is_active",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("start_date") and cleaned.get("end_date") and cleaned["end_date"] < cleaned["start_date"]:
            self.add_error("end_date", "End date must be on or after the start date.")
        if cleaned.get("discount_value") is not None and cleaned["discount_value"] < 0:
            self.add_error("discount_value", "Discount cannot be negative.")
        if cleaned.get("discount_type") == Coupon.DiscountType.PERCENTAGE and cleaned.get("discount_value") is not None and cleaned["discount_value"] > 100:
            self.add_error("discount_value", "Percentage discount cannot exceed 100%.")
        return cleaned


class BlogManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ["title", "category", "image", "excerpt", "content", "status"]
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "content": forms.Textarea(attrs={"rows": 14}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class BlogCategoryManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = BlogCategory
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class WarehouseManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["code", "name", "address", "pincode", "is_active"]
        widgets = {"address": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class InventoryBatchManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = InventoryBatch
        fields = [
            "vendor_product",
            "warehouse",
            "batch_number",
            "manufactured_on",
            "expires_on",
            "quantity",
            "reserved_quantity",
            "mrp",
            "supplier_name",
            "supplier_invoice_number",
            "dispensing_pharmacy",
            "storage_min_celsius",
            "storage_max_celsius",
            "excursion_status",
            "is_quarantined",
            "quarantine_reason",
            "recall_reference",
        ]
        widgets = {
            "manufactured_on": forms.DateInput(attrs={"type": "date"}),
            "expires_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        quantity = cleaned.get("quantity")
        reserved = cleaned.get("reserved_quantity")
        if quantity is not None and reserved is not None and reserved > quantity:
            self.add_error("reserved_quantity", "Reserved quantity cannot exceed total quantity.")
        if cleaned.get("manufactured_on") and cleaned.get("expires_on") and cleaned["expires_on"] <= cleaned["manufactured_on"]:
            self.add_error("expires_on", "Expiry date must be after the manufacturing date.")
        if cleaned.get("mrp") is not None and cleaned["mrp"] < 0:
            self.add_error("mrp", "MRP cannot be negative.")
        min_temp = cleaned.get("storage_min_celsius")
        max_temp = cleaned.get("storage_max_celsius")
        if min_temp is not None and max_temp is not None and min_temp > max_temp:
            self.add_error("storage_max_celsius", "Maximum storage temperature must be at least the minimum.")
        return cleaned


class InventoryTemperatureLogManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = InventoryTemperatureLog
        fields = ["batch", "temperature_celsius", "recorded_at", "source", "is_excursion", "note"]
        widgets = {"recorded_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        batch = cleaned.get("batch")
        temperature = cleaned.get("temperature_celsius")
        if batch and temperature is not None:
            lower, upper = batch.storage_min_celsius, batch.storage_max_celsius
            outside_range = (lower is not None and temperature < lower) or (upper is not None and temperature > upper)
            if outside_range and not cleaned.get("is_excursion"):
                self.add_error("is_excursion", "Mark this reading as an excursion because it is outside the batch range.")
        return cleaned


class RecallNoticeManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RecallNotice
        fields = [
            "product", "batch", "reference", "reason", "status", "reverse_pickup_required",
            "regulatory_report_reference",
        ]
        widgets = {"reason": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        batch = cleaned.get("batch")
        product = cleaned.get("product")
        if batch and product and batch.vendor_product.product_id != product.pk:
            self.add_error("batch", "The selected batch belongs to a different product.")
        return cleaned


class PharmacistProfileManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PharmacistProfile
        fields = [
            "user", "full_name", "registration_number", "licensing_authority", "pharmacy_name",
            "pharmacy_license_number", "state", "credential_document", "is_verified",
        ]

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class QualityComplaintManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = QualityComplaint
        fields = ["user", "product", "order", "batch_number", "description", "evidence", "status", "resolution_note"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "resolution_note": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class DispensingRecordManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DispensingRecord
        fields = [
            "order_item", "prescription_item", "pharmacist", "pharmacy_license_number", "batch", "quantity",
            "substitution_made", "substitution_details", "original_prescription_checked",
            "patient_identity_checked", "notes", "dispensed_at",
        ]
        widgets = {"substitution_details": forms.Textarea(attrs={"rows": 3}), "notes": forms.Textarea(attrs={"rows": 3}), "dispensed_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, **kwargs):
        self.actor = kwargs.pop("actor", None)
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        order_item = cleaned.get("order_item")
        batch = cleaned.get("batch")
        quantity = cleaned.get("quantity")
        if order_item and quantity and quantity > order_item.quantity:
            self.add_error("quantity", "Dispensed quantity cannot exceed the order quantity.")
        if order_item and batch and batch.vendor_product.product_id != order_item.product_id:
            self.add_error("batch", "The batch must belong to the ordered product.")
        if cleaned.get("substitution_made") and not cleaned.get("substitution_details"):
            self.add_error("substitution_details", "Describe the approved substitution.")
        return cleaned


class ShipmentManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Shipment
        fields = [
            "order",
            "warehouse",
            "courier_name",
            "tracking_number",
            "status",
            "promised_at",
            "shipped_at",
            "delivered_at",
        ]
        widgets = {
            "promised_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "shipped_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "delivered_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_status(self):
        status = self.cleaned_data["status"]
        if not self.instance.pk or status == self.instance.status:
            return status
        allowed = {
            Shipment.Status.PENDING: {Shipment.Status.BOOKED, Shipment.Status.EXCEPTION},
            Shipment.Status.BOOKED: {Shipment.Status.IN_TRANSIT, Shipment.Status.EXCEPTION},
            Shipment.Status.IN_TRANSIT: {Shipment.Status.OUT_FOR_DELIVERY, Shipment.Status.EXCEPTION, Shipment.Status.RETURNED},
            Shipment.Status.OUT_FOR_DELIVERY: {Shipment.Status.DELIVERED, Shipment.Status.EXCEPTION, Shipment.Status.RETURNED},
            Shipment.Status.EXCEPTION: {Shipment.Status.BOOKED, Shipment.Status.RETURNED},
            Shipment.Status.DELIVERED: set(),
            Shipment.Status.RETURNED: set(),
        }
        if status not in allowed.get(self.instance.status, set()):
            raise ValidationError("That shipment status transition is not allowed.")
        return status


class LabTestManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LabTest
        fields = [
            "partner",
            "name",
            "image",
            "category",
            "description",
            "sample_type",
            "preparation",
            "report_sla_hours",
            "price",
            "mrp",
            "is_home_collection",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "preparation": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class VendorManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            "user", "business_name", "owner_name", "email", "phone", "address",
            "gst_number", "license_number", "business_type", "bank_name",
            "bank_account_number", "ifsc_code", "documents", "is_approved", "is_active",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class VendorProductManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = VendorProduct
        fields = [
            "vendor", "product", "price", "stock_quantity", "delivery_time",
            "warranty", "offer_text", "seller_rating", "is_active", "is_approved",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("price")
        product = cleaned.get("product")
        if price is not None and product and price > product.mrp:
            self.add_error("price", "Seller price cannot exceed the product MRP.")
        return cleaned


class BusinessLicenseManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = BusinessLicense
        fields = [
            "vendor", "license_type", "license_number", "form_number", "legal_name",
            "premises_address", "state", "licensing_authority", "issued_on", "valid_until",
            "document", "status", "verification_source", "review_notes",
        ]
        widgets = {
            "issued_on": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
            "premises_address": forms.Textarea(attrs={"rows": 4}),
            "review_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class DoctorManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DoctorProfile
        fields = [
            "user", "full_name", "specialization", "registration_number", "medical_council",
            "qualification", "qualification_document", "experience_years", "clinic_name",
            "clinic_address", "phone", "consultation_fee", "availability", "is_verified",
        ]
        widgets = {"clinic_address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class LabPartnerManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LabPartner
        fields = ["name", "city", "address", "accreditations", "licence_number", "quality_document", "operating_hours", "service_area_pincodes", "phone", "website", "is_active"]
        widgets = {"address": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class LabBookingManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LabBooking
        fields = [
            "user", "dependent", "lab_test", "address", "status", "scheduled_start",
            "scheduled_end", "slot", "phlebotomist", "collection_otp", "accession_number", "report_file",
            "report_summary", "report_ready_at", "identity_verified_at", "collection_proof", "sample_collected_at", "cancellation_reason",
        ]
        widgets = {
            "scheduled_start": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "scheduled_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "report_ready_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "report_summary": forms.Textarea(attrs={"rows": 4}),
            "cancellation_reason": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class LabCollectionSlotManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LabCollectionSlot
        fields = ["partner", "starts_at", "ends_at", "capacity", "booked_count", "is_blackout", "is_active"]
        widgets = {"starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("starts_at") and cleaned.get("ends_at") and cleaned["ends_at"] <= cleaned["starts_at"]:
            self.add_error("ends_at", "Slot end must be after slot start.")
        if cleaned.get("capacity") is not None and cleaned.get("booked_count") is not None and cleaned["booked_count"] > cleaned["capacity"]:
            self.add_error("booked_count", "Booked count cannot exceed slot capacity.")
        return cleaned


class ConsultationManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Consultation
        fields = [
            "user", "dependent", "doctor", "mode", "status", "symptoms", "patient_history",
            "fee", "consent_at", "scheduled_at", "followup_until", "clinical_notes",
            "advice", "e_prescription",
        ]
        widgets = {
            "symptoms": forms.Textarea(attrs={"rows": 4}),
            "patient_history": forms.Textarea(attrs={"rows": 4}),
            "clinical_notes": forms.Textarea(attrs={"rows": 4}),
            "advice": forms.Textarea(attrs={"rows": 4}),
            "consent_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "followup_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class OrderManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Order
        fields = ["delivery_staff", "order_status", "cancellation_reason"]
        widgets = {"cancellation_reason": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class PaymentManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["status", "gateway_status", "failure_code", "failure_description", "last_gateway_check_at"]
        widgets = {
            "failure_description": forms.Textarea(attrs={"rows": 3}),
            "last_gateway_check_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class RefundManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Refund
        fields = ["amount", "reason", "status", "gateway_refund_id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class ReturnRequestManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ReturnRequest
        fields = [
            "status",
            "quantity",
            "refund_amount",
            "inspection_decision",
            "pickup_reference",
            "resolution_note",
            "reviewed_by",
            "inspected_by",
            "inspected_at",
        ]
        widgets = {"resolution_note": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class NotificationManagementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Notification
        fields = ["user", "title", "message", "notification_type", "link", "is_read"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
