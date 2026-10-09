from django import forms

from .models import Brand, Category, Product


class ProductFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search")
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label="All categories",
    )
    brand = forms.ModelChoiceField(
        queryset=Brand.objects.filter(is_active=True),
        required=False,
        empty_label="All brands",
    )
    product_type = forms.ChoiceField(
        choices=[("", "All product types")] + list(Product.ProductType.choices),
        required=False,
    )
    min_price = forms.DecimalField(required=False, min_value=0, decimal_places=2)
    max_price = forms.DecimalField(required=False, min_value=0, decimal_places=2)
    prescription = forms.ChoiceField(
        choices=[
            ("", "Prescription status"),
            ("required", "Prescription required"),
            ("not_required", "No prescription required"),
        ],
        required=False,
    )
    sort = forms.ChoiceField(
        choices=[
            ("newest", "Newest"),
            ("price_low", "Price Low to High"),
            ("price_high", "Price High to Low"),
            ("discount", "Best Discount"),
        ],
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["category"].widget.attrs["class"] = "form-select"
        self.fields["brand"].widget.attrs["class"] = "form-select"
        self.fields["product_type"].widget.attrs["class"] = "form-select"
        self.fields["prescription"].widget.attrs["class"] = "form-select"
        self.fields["sort"].widget.attrs["class"] = "form-select"
