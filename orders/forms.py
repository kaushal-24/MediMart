from django import forms
from django.core.validators import RegexValidator

from accounts.models import Address
from .models import Order, ReturnRequest


class CheckoutForm(forms.Form):
    address = forms.ModelChoiceField(queryset=Address.objects.none())
    coupon_code = forms.CharField(max_length=30, required=False)
    payment_method = forms.ChoiceField(
        choices=[
            (Order.PaymentMethod.COD, "Cash on Delivery"),
            (Order.PaymentMethod.RAZORPAY, "Razorpay Online Payment"),
        ]
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            addresses = user.addresses.all()
            self.fields["address"].queryset = addresses
            if not self.is_bound:
                default_address = addresses.filter(is_default=True).first() or addresses.first()
                if default_address:
                    self.initial["address"] = default_address
        if not self.is_bound:
            self.initial.setdefault("payment_method", Order.PaymentMethod.RAZORPAY)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["address"].widget.attrs["class"] = "form-select"
        self.fields["payment_method"].widget.attrs["class"] = "form-select"


class PaymentContactForm(forms.Form):
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(
        max_length=20,
        validators=[RegexValidator(r"^\+?[0-9\s-]{10,19}$", "Enter a valid phone number.")],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({"class": "form-control", "autocomplete": "email"})
        self.fields["phone"].widget.attrs.update({"class": "form-control", "autocomplete": "tel", "inputmode": "tel"})


class ReturnRequestForm(forms.ModelForm):
    class Meta:
        model = ReturnRequest
        fields = ["reason", "quantity", "description", "evidence"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["quantity"].help_text = "Choose how many units from this order line you want to return."
        self.fields["quantity"].widget.attrs.update({"min": 1, "inputmode": "numeric"})
