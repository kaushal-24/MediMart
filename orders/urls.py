from django.urls import path

from . import views


app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/invoice/", views.invoice_detail, name="invoice_detail"),
    path("orders/<int:pk>/invoice.pdf", views.invoice_pdf, name="invoice_pdf"),
    path("orders/<int:pk>/pay/", views.payment_start, name="payment_start"),
    path("orders/<int:pk>/pay/verify/", views.payment_verify, name="payment_verify"),
    path("orders/<int:pk>/cancel/", views.cancel_order, name="cancel_order"),
    path("payments/razorpay/webhook/", views.payment_webhook, name="payment_webhook"),
]
