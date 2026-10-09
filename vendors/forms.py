from django import forms

from products.models import Product

from .models import BusinessLicense, Vendor, VendorProduct


class BootstrapModelForm(forms.ModelForm):
    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class VendorRegistrationForm(BootstrapModelForm):
    license_type = forms.ChoiceField(choices=BusinessLicense.LicenseType.choices)
    license_form_number = forms.CharField(max_length=40, required=False)
    license_legal_name = forms.CharField(max_length=200, required=False)
    license_state = forms.CharField(max_length=100, required=False)
    license_issued_on = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    license_valid_until = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    license_document = forms.FileField(required=False)
    class Meta:
        model = Vendor
        fields = [
            "business_name",
            "owner_name",
            "email",
            "phone",
            "address",
            "gst_number",
            "license_number",
            "business_type",
            "bank_name",
            "bank_account_number",
            "ifsc_code",
            "documents",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_license_number(self):
        return self.cleaned_data["license_number"].strip().upper()


class BusinessLicenseForm(BootstrapModelForm):
    class Meta:
        model = BusinessLicense
        fields = [
            "license_type",
            "license_number",
            "form_number",
            "legal_name",
            "premises_address",
            "state",
            "licensing_authority",
            "issued_on",
            "valid_until",
            "document",
        ]
        widgets = {
            "premises_address": forms.Textarea(attrs={"rows": 3}),
            "issued_on": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_license_number(self):
        return self.cleaned_data["license_number"].strip().upper()


class VendorProductForm(BootstrapModelForm):
    class Meta:
        model = VendorProduct
        fields = [
            "product",
            "price",
            "stock_quantity",
            "delivery_time",
            "warranty",
            "offer_text",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True).order_by("name")
        self.apply_bootstrap_classes()


class VendorCatalogProductForm(BootstrapModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "category",
            "brand",
            "product_type",
            "image",
            "short_description",
            "description",
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
            "unit",
            "weight",
            "dimensions",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "regulatory_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["required_license_type"].required = False
        self.apply_bootstrap_classes()

    def clean(self):
        cleaned_data = super().clean()
        requires_license = cleaned_data.get("requires_business_license", False)
        license_type = cleaned_data.get("required_license_type") or Product.RegulationType.NONE
        if requires_license and license_type == Product.RegulationType.NONE:
            self.add_error(
                "required_license_type",
                "Select the licence category required to sell this regulated product.",
            )
        if not requires_license:
            cleaned_data["required_license_type"] = Product.RegulationType.NONE
        return cleaned_data
