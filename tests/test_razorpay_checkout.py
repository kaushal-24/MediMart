import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Address
from orders.models import Order, Payment, PaymentEvent


User = get_user_model()


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_example",
    RAZORPAY_KEY_SECRET="test-secret",
    RAZORPAY_CURRENCY="INR",
)
class RazorpayCheckoutTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="razorpay-customer",
            email="razorpay.customer@gmail.com",
            password="Testpass123!",
        )
        self.address = Address.objects.create(
            user=self.customer,
            full_name="Razorpay Customer",
            phone="9999999999",
            address_line_1="Test Street",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            address_snapshot="Razorpay Customer\nTest Street",
            subtotal=Decimal("100.00"),
            discount=Decimal("0.00"),
            delivery_charge=Decimal("49.00"),
            total_amount=Decimal("149.00"),
            payment_method=Order.PaymentMethod.RAZORPAY,
            order_status=Order.OrderStatus.PENDING,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            payment_method=Order.PaymentMethod.RAZORPAY,
            amount=self.order.total_amount,
        )
        self.client.force_login(self.customer)

    @patch("orders.views.create_razorpay_order")
    def test_create_order_returns_standard_checkout_payload(self, create_order):
        create_order.return_value = {
            "id": "order_test_123",
            "amount": 14900,
            "currency": "INR",
        }

        response = self.client.post(
            reverse("orders:payment_create_order", args=[self.order.pk]),
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "order_id": "order_test_123",
                "amount": 14900,
                "currency": "INR",
            },
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.gateway_order_id, "order_test_123")
        self.assertTrue(PaymentEvent.objects.filter(event_type="gateway_order_created").exists())

    @patch("orders.views.create_razorpay_order")
    def test_create_order_rejects_amount_below_gateway_minimum(self, create_order):
        self.order.total_amount = Decimal("0.50")
        self.order.save(update_fields=["total_amount"])

        response = self.client.post(
            reverse("orders:payment_create_order", args=[self.order.pk]),
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("at least 100 paise", response.json()["error"])
        create_order.assert_not_called()

    def test_verify_rejects_signature_mismatch_without_marking_payment_paid(self):
        self.payment.gateway_order_id = "order_test_123"
        self.payment.save(update_fields=["gateway_order_id"])

        response = self.client.post(
            reverse("orders:payment_verify", args=[self.order.pk]),
            {
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": "pay_test_123",
                "razorpay_signature": "invalid",
            },
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Order.PaymentStatus.PENDING)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
        self.assertTrue(
            PaymentEvent.objects.filter(event_type="verification_rejected").exists()
        )

    def test_payment_failure_is_recorded_without_marking_order_paid(self):
        self.payment.gateway_order_id = "order_test_123"
        self.payment.save(update_fields=["gateway_order_id"])

        response = self.client.post(
            reverse("orders:payment_failure", args=[self.order.pk]),
            data=json.dumps(
                {
                    "razorpay_order_id": "order_test_123",
                    "razorpay_payment_id": "pay_test_123",
                    "error": {"code": "BAD_REQUEST_ERROR", "description": "Payment cancelled."},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Order.PaymentStatus.FAILED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        self.assertTrue(PaymentEvent.objects.filter(event_type="browser_payment_failed").exists())

    def test_payment_failure_cannot_downgrade_a_refunded_payment(self):
        self.payment.gateway_order_id = "order_test_123"
        self.payment.status = Order.PaymentStatus.REFUNDED
        self.payment.save(update_fields=["gateway_order_id", "status"])
        self.order.payment_status = Order.PaymentStatus.REFUNDED
        self.order.save(update_fields=["payment_status"])

        response = self.client.post(
            reverse("orders:payment_failure", args=[self.order.pk]),
            data=json.dumps(
                {
                    "razorpay_order_id": "order_test_123",
                    "razorpay_payment_id": "pay_test_123",
                    "error": {"code": "BAD_REQUEST_ERROR", "description": "Late failure event."},
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)

    @patch("orders.views.get_razorpay_client")
    def test_verify_accepts_valid_signature_and_captured_payment(self, get_client):
        self.payment.gateway_order_id = "order_test_123"
        self.payment.save(update_fields=["gateway_order_id"])
        payment_id = "pay_test_123"
        signature = hmac.new(
            b"test-secret",
            b"order_test_123|pay_test_123",
            hashlib.sha256,
        ).hexdigest()
        client = MagicMock()
        client.payment.fetch.return_value = {
            "id": payment_id,
            "order_id": "order_test_123",
            "amount": 14900,
            "currency": "INR",
            "status": "captured",
        }
        get_client.return_value = client

        response = self.client.post(
            reverse("orders:payment_verify", args=[self.order.pk]),
            {
                "razorpay_order_id": "order_test_123",
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            },
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Order.PaymentStatus.PAID)
        self.assertEqual(self.payment.gateway_payment_id, payment_id)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        client.utility.verify_payment_signature.assert_called_once()

    def test_payment_page_loads_checkout_script_and_create_endpoint(self):
        response = self.client.get(reverse("orders:payment_start", args=[self.order.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://checkout.razorpay.com/v1/checkout.js")
        self.assertContains(
            response,
            reverse("orders:payment_create_order", args=[self.order.pk]),
        )
        self.assertContains(response, 'payment.failed')
        self.assertContains(response, "ondismiss")
