from django import forms

from accounts.models import Address
from .models import Order


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
            self.fields["address"].queryset = user.addresses.all()
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["address"].widget.attrs["class"] = "form-select"
        self.fields["payment_method"].widget.attrs["class"] = "form-select"
