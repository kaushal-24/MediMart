from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, UserProfile
from cart.models import Cart, CartItem
from extras.models import Notification, SupportMessage, SupportTicket
from orders.models import Order
from prescriptions.forms import PrescriptionUploadForm
from products.models import Brand, Category, Product
from vendors.models import Vendor, VendorProduct


User = get_user_model()


class Phase13SecurityTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="customer",
            email="customer@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.customer, role=UserProfile.Role.CUSTOMER)
        self.other_customer = User.objects.create_user(
            username="other_customer",
            email="other@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.other_customer, role=UserProfile.Role.CUSTOMER)
        self.staff = User.objects.create_user(
            username="staff",
            email="staff@gmail.com",
            password="Testpass123!",
            is_staff=True,
        )
        UserProfile.objects.create(user=self.staff, role=UserProfile.Role.SUPPORT_STAFF)

        self.address = Address.objects.create(
            user=self.customer,
            full_name="MediMart Customer",
            phone="9999999999",
            address_line_1="Test Street",
            city="Test City",
            state="Test State",
            pincode="123456",
            is_default=True,
        )
        self.category = Category.objects.create(name="Test Care", slug="test-care")
        self.brand = Brand.objects.create(name="Test Brand", slug="test-brand")
        self.product = Product.objects.create(
            name="Test Thermometer",
            slug="test-thermometer",
            sku="TEST-THERMO",
            category=self.category,
            brand=self.brand,
            product_type=Product.ProductType.MEDICAL_EQUIPMENT,
            description="A test thermometer.",
            mrp=Decimal("1000.00"),
            selling_price=Decimal("800.00"),
            stock_quantity=10,
            is_active=True,
        )
        self.rx_product = Product.objects.create(
            name="Test Prescription Tablet",
            slug="test-prescription-tablet",
            sku="TEST-RX",
            category=self.category,
            brand=self.brand,
            product_type=Product.ProductType.MEDICINE,
            description="A prescription-required test medicine.",
            mrp=Decimal("200.00"),
            selling_price=Decimal("150.00"),
            stock_quantity=10,
            requires_prescription=True,
            is_active=True,
        )
        self.vendor_user = User.objects.create_user(
            username="vendor",
            email="vendor@gmail.com",
            password="Testpass123!",
        )
        self.vendor = Vendor.objects.create(
            user=self.vendor_user,
            business_name="Test Pharmacy",
            owner_name="Vendor Owner",
            email="vendor@gmail.com",
            phone="8888888888",
            address="Vendor Street",
            license_number="LIC-123",
            business_type=Vendor.BusinessType.PHARMACY,
            is_approved=True,
            is_active=True,
        )
        self.offer = VendorProduct.objects.create(
            vendor=self.vendor,
            product=self.product,
            price=Decimal("750.00"),
            stock_quantity=5,
            is_active=True,
            is_approved=True,
        )
        self.rx_offer = VendorProduct.objects.create(
            vendor=self.vendor,
            product=self.rx_product,
            price=Decimal("140.00"),
            stock_quantity=5,
            is_active=True,
            is_approved=True,
        )

    def test_order_detail_is_private_to_customer(self):
        order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            address_snapshot="MediMart Customer\nTest Street",
            subtotal=Decimal("750.00"),
            discount=Decimal("0.00"),
            delivery_charge=Decimal("49.00"),
            total_amount=Decimal("799.00"),
            payment_method=Order.PaymentMethod.COD,
        )

        self.client.login(username="other_customer", password="Testpass123!")
        response = self.client.get(reverse("orders:order_detail", args=[order.pk]))

        self.assertEqual(response.status_code, 404)

    def test_prescription_upload_form_rejects_future_dates_and_large_files(self):
        future_file = SimpleUploadedFile("rx.pdf", b"small", content_type="application/pdf")
        future_form = PrescriptionUploadForm(
            data={"prescription_date": timezone.localdate() + timedelta(days=1)},
            files={"file": future_file},
        )

        self.assertFalse(future_form.is_valid())
        self.assertIn("prescription_date", future_form.errors)

        large_file = SimpleUploadedFile(
            "large-rx.pdf",
            b"x" * ((5 * 1024 * 1024) + 1),
            content_type="application/pdf",
        )
        large_form = PrescriptionUploadForm(files={"file": large_file})

        self.assertFalse(large_form.is_valid())
        self.assertIn("file", large_form.errors)

    def test_prescription_required_product_cannot_be_added_without_approval(self):
        self.client.login(username="customer", password="Testpass123!")

        response = self.client.post(reverse("cart:add_to_cart", args=[self.rx_offer.pk]))

        self.assertRedirects(response, reverse("prescriptions:prescription_upload"))
        self.assertFalse(CartItem.objects.filter(cart__user=self.customer).exists())

    def test_support_ticket_is_private_but_staff_can_reply(self):
        ticket = SupportTicket.objects.create(
            user=self.customer,
            subject="Need help",
            category=SupportTicket.Category.ORDER,
            message="Please check my order.",
        )

        self.client.login(username="other_customer", password="Testpass123!")
        response = self.client.get(reverse("extras:support_ticket_detail", args=[ticket.pk]))
        self.assertEqual(response.status_code, 404)

        self.client.logout()
        self.client.login(username="staff", password="Testpass123!")
        response = self.client.post(
            reverse("extras:support_ticket_detail", args=[ticket.pk]),
            {"message": "We are checking this for you."},
        )
        ticket.refresh_from_db()

        self.assertRedirects(response, reverse("extras:support_ticket_detail", args=[ticket.pk]))
        self.assertEqual(ticket.status, SupportTicket.Status.IN_PROGRESS)
        self.assertTrue(
            SupportMessage.objects.filter(ticket=ticket, sender=self.staff, is_staff_reply=True).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.customer,
                notification_type=Notification.NotificationType.SUPPORT,
            ).exists()
        )

    def test_product_compare_uses_session_selection(self):
        response = self.client.post(
            reverse("products:compare_add", args=[self.product.pk]),
            {"next": reverse("products:product_compare")},
        )

        self.assertRedirects(response, reverse("products:product_compare"))
        response = self.client.get(reverse("products:product_compare"))
        self.assertContains(response, self.product.name)

    def test_dark_mode_toggle_is_available_site_wide(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, 'id="themeToggle"')
        self.assertContains(response, "medimart-theme")

    def test_checkout_creates_order_and_notification(self):
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, vendor_product=self.offer, quantity=1)
        self.client.login(username="customer", password="Testpass123!")

        response = self.client.post(
            reverse("orders:checkout"),
            {
                "address": self.address.pk,
                "coupon_code": "",
                "payment_method": Order.PaymentMethod.COD,
            },
        )

        order = Order.objects.get(customer=self.customer)
        self.assertRedirects(response, reverse("orders:order_detail", args=[order.pk]))
        self.assertTrue(
            Notification.objects.filter(
                user=self.customer,
                notification_type=Notification.NotificationType.ORDER,
            ).exists()
        )
