from decimal import Decimal
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from core.checkout import CheckoutConfig
from extras.services import (
    format_whatsapp_notification,
    send_whatsapp_message,
    send_whatsapp_notification,
    whatsapp_destination,
)
from orders.pricing import calculate_order_charges


class OrderPricingTests(SimpleTestCase):
    @patch("orders.pricing.get_checkout_config")
    def test_configured_charges_are_added_to_customer_total(self, get_checkout_config):
        get_checkout_config.return_value = CheckoutConfig(
            delivery_fee=Decimal("49"),
            free_delivery=False,
            tax_rate_percent=Decimal("18"),
            handling_fee=Decimal("12.50"),
            platform_fee=Decimal("5"),
            cold_chain_fee=Decimal("25"),
            cod_max_order_value=Decimal("5000"),
            cod_blocked_pincodes=frozenset(),
        )
        item = SimpleNamespace(
            total_price=Decimal("1000.00"),
            vendor_product=SimpleNamespace(
                product=SimpleNamespace(cold_chain_required=True),
            ),
        )
        coupon = SimpleNamespace(calculate_discount=lambda subtotal: Decimal("100.00"))

        charges = calculate_order_charges([item], coupon)

        self.assertEqual(charges["subtotal"], Decimal("1000.00"))
        self.assertEqual(charges["discount"], Decimal("100.00"))
        self.assertEqual(charges["tax_amount"], Decimal("162.00"))
        self.assertEqual(charges["handling_charge"], Decimal("12.50"))
        self.assertEqual(charges["platform_fee"], Decimal("5.00"))
        self.assertEqual(charges["delivery_charge"], Decimal("49.00"))
        self.assertTrue(charges["cold_chain_required"])
        self.assertEqual(charges["cold_chain_charge"], Decimal("25.00"))
        self.assertEqual(charges["total_amount"], Decimal("1153.50"))


class NotificationLinkTests(SimpleTestCase):
    @override_settings(PUBLIC_SITE_URL="http://127.0.0.1:8000")
    @patch("extras.services.send_whatsapp_message", return_value=True)
    def test_whatsapp_notification_contains_the_in_app_destination(self, send_message):
        self.assertTrue(
            send_whatsapp_notification(
                "919876543210@c.us",
                "Order update",
                "Your order is ready.",
                "/orders/123/",
            )
        )

        send_message.assert_called_once_with(
            "919876543210@c.us",
            "*Order update*\n\nYour order is ready.\n\n*Click Here To Open Website:*\n"
            "http://127.0.0.1:8000/orders/123/",
        )

    def test_whatsapp_notification_highlights_otp_and_order_number(self):
        message = format_whatsapp_notification(
            "Order update",
            "Order MMABC123456 is ready. Your OTP is 123456.",
        )

        self.assertEqual(
            message,
            "*Order update*\n\nOrder *MMABC123456* is ready. Your OTP is *123456*.",
        )

    def test_whatsapp_notification_highlights_common_reference_numbers(self):
        message = format_whatsapp_notification(
            "Support update",
            "Ticket #42 and prescription #18 are ready for review.",
        )

        self.assertEqual(
            message,
            "*Support update*\n\n*Ticket #42* and *prescription #18* are ready for review.",
        )

    def test_whatsapp_destination_accepts_a_default_address_phone(self):
        user = SimpleNamespace(
            phone_number="",
            profile=SimpleNamespace(phone_number=""),
            addresses=SimpleNamespace(
                order_by=lambda *args: SimpleNamespace(
                    values_list=lambda *fields, **kwargs: ["+91 98765 43210"]
                )
            ),
        )

        self.assertEqual(whatsapp_destination(user), "919876543210@c.us")

    @override_settings(
        WHATSAPP_PROVIDER="openwa",
        WHATSAPP_API_URL="http://127.0.0.1:2785/api",
        WHATSAPP_API_KEY="test-key",
        WHATSAPP_SESSION_ID="session-id",
        WHATSAPP_TIMEOUT_SECONDS=1,
    )
    @patch("extras.services.urlopen")
    def test_whatsapp_message_requires_a_ready_openwa_session(self, urlopen_mock):
        class Response:
            def __init__(self, payload, status=200):
                self.status = status
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        urlopen_mock.return_value = Response({"status": "qr_ready", "phone": None})
        self.assertFalse(send_whatsapp_message("919876543210@c.us", "Test"))
        self.assertEqual(urlopen_mock.call_count, 1)

        urlopen_mock.reset_mock()
        urlopen_mock.side_effect = [
            Response({"status": "ready", "phone": "919876543210"}),
            Response({"ok": True}, status=201),
        ]
        self.assertTrue(send_whatsapp_message("919876543210@c.us", "Test"))
        self.assertEqual(urlopen_mock.call_count, 2)
