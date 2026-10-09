from datetime import timedelta
from decimal import Decimal

import pyotp
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, UserProfile
from extras.models import Notification, NotificationDelivery
from extras.services import create_notification
from orders.models import Order, OrderItem, Payment
from prescriptions.models import Prescription, PrescriptionItem
from products.models import Brand, Category, Product
from reviews.views import can_user_review_product
from vendors.models import BusinessLicense, Vendor, VendorProduct


User = get_user_model()


class IndustrialHardeningTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="secure_customer",
            email="secure.customer@gmail.com",
            password="Testpass123!",
        )
        self.profile = UserProfile.objects.create(
            user=self.customer,
            role=UserProfile.Role.CUSTOMER,
            phone_number="9999999999",
        )
        self.other = User.objects.create_user(
            username="other_secure_customer",
            email="other.secure@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.other, role=UserProfile.Role.CUSTOMER)
        self.vendor_user = User.objects.create_user(
            username="secure_vendor",
            email="secure.vendor@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.vendor_user, role=UserProfile.Role.VENDOR)
        self.category = Category.objects.create(name="Hardening", slug="hardening")
        self.brand = Brand.objects.create(name="Secure Brand", slug="secure-brand")
        self.product = Product.objects.create(
            name="Secure Medicine",
            slug="secure-medicine",
            sku="SECURE-RX-1",
            category=self.category,
            brand=self.brand,
            product_type=Product.ProductType.MEDICINE,
            description="Test medicine",
            mrp=Decimal("120.00"),
            selling_price=Decimal("100.00"),
            stock_quantity=99,
            requires_prescription=True,
        )
        self.vendor = Vendor.objects.create(
            user=self.vendor_user,
            business_name="Secure Pharmacy",
            owner_name="Owner",
            email="secure.vendor@gmail.com",
            phone="8888888888",
            address="Test address",
            license_number="SEC-LIC-1",
            business_type=Vendor.BusinessType.PHARMACY,
            bank_account_number="123456789012",
            is_approved=True,
            is_active=True,
        )
        self.offer = VendorProduct.objects.create(
            vendor=self.vendor,
            product=self.product,
            price=Decimal("90.00"),
            stock_quantity=5,
            is_active=True,
            is_approved=True,
        )
        self.address = Address.objects.create(
            user=self.customer,
            full_name="Secure Customer",
            phone="9999999999",
            address_line_1="Test Street",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
        )

    def test_private_prescription_download_is_owner_only(self):
        prescription = Prescription.objects.create(
            user=self.customer,
            file=SimpleUploadedFile("rx.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        self.client.login(username=self.customer.username, password="Testpass123!")
        owner_response = self.client.get(reverse("core:prescription_file", args=[prescription.pk]))
        self.assertEqual(owner_response.status_code, 200)

        self.client.logout()
        self.client.login(username=self.other.username, password="Testpass123!")
        other_response = self.client.get(reverse("core:prescription_file", args=[prescription.pk]))
        self.assertEqual(other_response.status_code, 403)

    def test_bank_account_is_encrypted_at_rest(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT bank_account_number FROM vendors_vendor WHERE id = %s", [self.vendor.pk])
            stored_value = cursor.fetchone()[0]
        self.assertTrue(stored_value.startswith("enc::"))
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.bank_account_number, "123456789012")

    def test_notification_creates_retryable_delivery_jobs(self):
        notification = create_notification(
            self.customer,
            "Order update",
            "Your order changed.",
            Notification.NotificationType.ORDER,
        )
        channels = set(notification.deliveries.values_list("channel", flat=True))
        self.assertEqual(
            channels,
            {NotificationDelivery.Channel.EMAIL, NotificationDelivery.Channel.SMS},
        )

    def test_mfa_challenges_login_and_accepts_current_totp(self):
        secret = pyotp.random_base32()
        self.profile.mfa_secret = secret
        self.profile.mfa_enabled = True
        self.profile.save(update_fields=["mfa_secret", "mfa_enabled"])

        login_response = self.client.post(
            reverse("accounts:login"),
            {"username": self.customer.username, "password": "Testpass123!"},
        )
        self.assertRedirects(login_response, reverse("accounts:mfa_challenge"))
        self.assertNotIn("_auth_user_id", self.client.session)

        verify_response = self.client.post(
            reverse("accounts:mfa_challenge"),
            {"code": pyotp.TOTP(secret).now()},
        )
        self.assertRedirects(verify_response, reverse("accounts:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.customer.pk)

    def test_catalog_api_uses_active_offer_stock_and_price(self):
        response = self.client.get(reverse("core:api_product_detail", args=[self.product.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["available_stock"], 5)
        self.assertEqual(response.json()["price"], "90")

    def test_review_requires_delivered_order(self):
        order = self._create_order(status=Order.OrderStatus.CONFIRMED)
        OrderItem.objects.create(
            order=order,
            vendor=self.vendor,
            product=self.product,
            vendor_product=self.offer,
            product_name=self.product.name,
            seller_name=self.vendor.business_name,
            sku=self.product.sku,
            quantity=1,
            unit_price=Decimal("90.00"),
            total_price=Decimal("90.00"),
        )
        self.assertFalse(can_user_review_product(self.customer, self.product))
        order.order_status = Order.OrderStatus.DELIVERED
        order.save(update_fields=["order_status"])
        self.assertTrue(can_user_review_product(self.customer, self.product))

    def test_customer_cancellation_restores_reserved_inventory(self):
        order = self._create_order(status=Order.OrderStatus.PENDING)
        OrderItem.objects.create(
            order=order,
            vendor=self.vendor,
            product=self.product,
            vendor_product=self.offer,
            product_name=self.product.name,
            seller_name=self.vendor.business_name,
            sku=self.product.sku,
            quantity=1,
            unit_price=Decimal("90.00"),
            total_price=Decimal("90.00"),
        )
        self.offer.stock_quantity = 4
        self.offer.save(update_fields=["stock_quantity"])
        Payment.objects.create(
            order=order,
            payment_method=Order.PaymentMethod.COD,
            amount=order.total_amount,
        )
        self.client.login(username=self.customer.username, password="Testpass123!")
        response = self.client.post(
            reverse("orders:cancel_order", args=[order.pk]),
            {"reason": "Ordered by mistake"},
        )
        self.assertRedirects(response, reverse("orders:order_detail", args=[order.pk]))
        order.refresh_from_db()
        self.offer.refresh_from_db()
        self.assertEqual(order.order_status, Order.OrderStatus.CANCELLED)
        self.assertEqual(self.offer.stock_quantity, 5)

    def test_expired_business_licence_is_not_current(self):
        licence = BusinessLicense.objects.create(
            vendor=self.vendor,
            license_type=BusinessLicense.LicenseType.DRUG_RETAIL,
            license_number="EXPIRED-1",
            status=BusinessLicense.Status.VERIFIED,
            valid_until=timezone.localdate() - timedelta(days=1),
        )
        self.assertFalse(licence.is_current)
        self.assertFalse(self.vendor.has_verified_license)

    def test_health_endpoints_report_live_and_ready(self):
        self.assertEqual(self.client.get(reverse("core:health_live")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:health_ready")).status_code, 200)

    def _create_order(self, status):
        return Order.objects.create(
            customer=self.customer,
            address=self.address,
            address_snapshot="Secure Customer\nTest Street",
            subtotal=Decimal("90.00"),
            discount=Decimal("0.00"),
            delivery_charge=Decimal("0.00"),
            total_amount=Decimal("90.00"),
            payment_method=Order.PaymentMethod.COD,
            order_status=status,
        )
