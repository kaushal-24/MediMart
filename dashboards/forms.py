from django import forms
from django.contrib.auth import get_user_model

from accounts.forms import BootstrapFormMixin
from accounts.models import UserProfile
from extras.models import BlogCategory, BlogPost
from orders.models import Coupon, InventoryBatch, Shipment, Warehouse
from products.models import Brand, Category, Product


User = get_user_model()


class UserManagementForm(BootstrapFormMixin, forms.ModelForm):
    role = forms.ChoiceField(choices=UserProfile.Role.choices)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, "profile", None)
        if profile:
            self.fields["role"].initial = profile.role
        self.apply_bootstrap_classes()

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
        ]
        widgets = {
            "manufactured_on": forms.DateInput(attrs={"type": "date"}),
            "expires_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


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
