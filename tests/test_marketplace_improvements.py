from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, UserProfile
from cart.models import Cart, CartItem
from extras.models import BlogCategory, BlogPost, SupportMessage, SupportTicket
from orders.models import Order, OrderItem, Payment
from products.models import Brand, Category, Product
from vendors.models import BusinessLicense, Vendor, VendorProduct


User = get_user_model()


class MarketplaceImprovementTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="customer",
            email="customer@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.customer, role=UserProfile.Role.CUSTOMER)
        self.vendor_user = User.objects.create_user(
            username="vendor",
            email="vendor@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.vendor_user, role=UserProfile.Role.MANUFACTURER)
        self.delivery_user = User.objects.create_user(
            username="delivery",
            email="delivery@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(
            user=self.delivery_user,
            role=UserProfile.Role.DELIVERY_STAFF,
        )
        self.staff = User.objects.create_user(
            username="staff",
            email="staff@gmail.com",
            password="Testpass123!",
            is_staff=True,
        )
        UserProfile.objects.create(user=self.staff, role=UserProfile.Role.ADMIN)
        self.address = Address.objects.create(
            user=self.customer,
            full_name="MediMart Customer",
            phone="9999999999",
            address_line_1="Test Street",
            city="Test City",
            state="Test State",
            pincode="123456",
        )
        self.category = Category.objects.create(name="Medical Equipment", slug="medical-equipment")
        self.brand = Brand.objects.create(name="LifeTrack", slug="lifetrack")
        self.product = Product.objects.create(
            name="Digital Blood Pressure Monitor",
            slug="digital-blood-pressure-monitor",
            sku="BP-001",
            category=self.category,
            brand=self.brand,
            product_type=Product.ProductType.MEDICAL_EQUIPMENT,
            description="Home blood pressure monitoring device.",
            mrp=Decimal("2000.00"),
            selling_price=Decimal("1500.00"),
            stock_quantity=10,
            is_active=True,
        )
        self.vendor = Vendor.objects.create(
            user=self.vendor_user,
            business_name="PulseCare Manufacturing",
            owner_name="Vendor Owner",
            email="vendor@gmail.com",
            phone="8888888888",
            address="Vendor Street",
            license_number="MFG-123",
            business_type=Vendor.BusinessType.MANUFACTURER,
            is_approved=True,
            is_active=True,
        )
        self.offer = VendorProduct.objects.create(
            vendor=self.vendor,
            product=self.product,
            price=Decimal("1450.00"),
            stock_quantity=5,
            is_active=True,
            is_approved=True,
        )

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_razorpay_checkout_requires_gateway_keys(self):
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, vendor_product=self.offer, quantity=1)
        self.client.login(username="customer", password="Testpass123!")

        response = self.client.post(
            reverse("orders:checkout"),
            {
                "address": self.address.pk,
                "coupon_code": "",
                "payment_method": Order.PaymentMethod.RAZORPAY,
            },
        )

        self.assertRedirects(response, reverse("orders:checkout"))
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())

    def test_vendor_can_submit_new_catalog_product_for_approval(self):
        self.client.login(username="vendor", password="Testpass123!")

        response = self.client.post(
            reverse("vendors:vendor_catalog_product_create"),
            {
                "name": "Portable Oxygen Concentrator",
                "sku": "OXY-001",
                "category": self.category.pk,
                "brand": self.brand.pk,
                "product_type": Product.ProductType.MEDICAL_EQUIPMENT,
                "short_description": "Compact home oxygen equipment.",
                "description": "Compact oxygen equipment for approved home-care use.",
                "mrp": "50000.00",
                "selling_price": "45000.00",
                "stock_quantity": "3",
                "manufacturer": "PulseCare Manufacturing",
            },
        )

        product = Product.objects.get(sku="OXY-001")
        self.assertRedirects(response, reverse("vendors:vendor_product_list"))
        self.assertFalse(product.is_active)
        self.assertTrue(VendorProduct.objects.filter(vendor=self.vendor, product=product).exists())

    def test_search_suggestions_returns_matching_products(self):
        response = self.client.get(reverse("products:search_suggestions"), {"q": "blood"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["name"], self.product.name)

    def test_pdf_invoice_download_returns_pdf(self):
        order = self.create_order(Order.OrderStatus.CONFIRMED)
        self.client.login(username="customer", password="Testpass123!")

        response = self.client.get(reverse("orders:invoice_pdf", args=[order.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_admin_can_assign_delivery_staff(self):
        order = self.create_order(Order.OrderStatus.SHIPPED)
        self.client.login(username="staff", password="Testpass123!")

        response = self.client.post(
            reverse("dashboards:assign_delivery_staff", args=[order.pk]),
            {"delivery_staff": self.delivery_user.pk},
        )

        order.refresh_from_db()
        self.assertRedirects(response, reverse("dashboards:admin_dashboard"))
        self.assertEqual(order.delivery_staff, self.delivery_user)

    def test_delivery_dashboard_only_shows_assigned_orders(self):
        assigned_order = self.create_order(Order.OrderStatus.OUT_FOR_DELIVERY)
        assigned_order.delivery_staff = self.delivery_user
        assigned_order.save(update_fields=["delivery_staff"])
        unassigned_order = self.create_order(Order.OrderStatus.OUT_FOR_DELIVERY)
        self.client.login(username="delivery", password="Testpass123!")

        response = self.client.get(reverse("dashboards:delivery_dashboard"))

        self.assertContains(response, assigned_order.order_number)
        self.assertNotContains(response, unassigned_order.order_number)

    def test_blog_list_shows_published_article(self):
        post = BlogPost.objects.create(
            title="How to Choose a BP Monitor",
            slug="how-to-choose-a-bp-monitor",
            excerpt="Practical guidance for home monitoring.",
            content="Use verified devices and follow clinician advice.",
            status=BlogPost.Status.PUBLISHED,
            published_at=timezone.now(),
            author=self.staff,
        )

        response = self.client.get(reverse("extras:blog_list"))

        self.assertContains(response, post.title)

    @patch("core.views.reverse_geocode")
    def test_detected_location_is_saved_to_session_and_profile(self, reverse_geocode_mock):
        reverse_geocode_mock.return_value = {
            "label": "Bengaluru, Karnataka 560001",
            "display_name": "MG Road, Bengaluru, Karnataka 560001",
            "address_line_1": "MG Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "pincode": "560001",
            "country": "India",
            "attribution": "Location data © OpenStreetMap contributors",
        }
        self.client.login(username="customer", password="Testpass123!")

        response = self.client.post(
            reverse("core:detect_location"),
            data=json.dumps({"latitude": 12.9716, "longitude": 77.5946, "accuracy": 25}),
            content_type="application/json",
        )

        self.customer.profile.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["location"]["pincode"], "560001")
        self.assertEqual(self.client.session["site_location"]["city"], "Bengaluru")
        self.assertEqual(self.customer.profile.preferred_pincode, "560001")

    def test_manual_location_validates_and_persists(self):
        invalid_response = self.client.post(
            reverse("core:set_manual_location"),
            {"city": "Bengaluru", "state": "Karnataka", "pincode": "123"},
        )
        valid_response = self.client.post(
            reverse("core:set_manual_location"),
            {"city": "Bengaluru", "state": "Karnataka", "pincode": "560001"},
        )

        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(valid_response.status_code, 200)
        self.assertEqual(self.client.session["site_location"]["label"], "Bengaluru, Karnataka 560001")

    def test_admin_can_publish_pending_catalog_offer(self):
        self.offer.is_approved = False
        self.offer.product.is_active = False
        self.offer.save(update_fields=["is_approved"])
        self.offer.product.save(update_fields=["is_active"])
        self.client.login(username="staff", password="Testpass123!")

        response = self.client.post(
            reverse("dashboards:review_offer", args=[self.offer.pk]),
            {"decision": "approve"},
        )

        self.offer.refresh_from_db()
        self.offer.product.refresh_from_db()
        self.assertRedirects(response, reverse("dashboards:admin_dashboard"))
        self.assertTrue(self.offer.is_approved)
        self.assertTrue(self.offer.product.is_active)

    def test_vendor_dashboard_reports_sales_from_order_lines(self):
        order = self.create_order(Order.OrderStatus.DELIVERED)
        Payment.objects.create(
            order=order,
            payment_method=Order.PaymentMethod.COD,
            amount=order.total_amount,
            status=Order.PaymentStatus.PAID,
        )
        self.client.login(username="vendor", password="Testpass123!")

        response = self.client.get(reverse("vendors:vendor_dashboard"))

        self.assertContains(response, "Recognized sales")
        self.assertContains(response, "1450.00")
        self.assertContains(response, order.order_number)

    def test_delivery_status_must_follow_operational_sequence(self):
        order = self.create_order(Order.OrderStatus.SHIPPED)
        order.delivery_staff = self.delivery_user
        order.save(update_fields=["delivery_staff"])
        self.client.login(username="delivery", password="Testpass123!")

        response = self.client.post(
            reverse("dashboards:update_delivery_order_status", args=[order.pk]),
            {"status": Order.OrderStatus.DELIVERED},
        )

        order.refresh_from_db()
        self.assertRedirects(response, reverse("dashboards:delivery_dashboard"))
        self.assertEqual(order.order_status, Order.OrderStatus.SHIPPED)

    def test_detected_address_components_are_persisted(self):
        self.client.login(username="customer", password="Testpass123!")
        response = self.client.post(
            reverse("accounts:address_create"),
            {
                "full_name": "MediMart Customer",
                "phone": "9999999999",
                "address_line_1": "42 MG Road",
                "address_line_2": "",
                "house_number": "42",
                "road": "MG Road",
                "neighbourhood": "Ashok Nagar",
                "suburb": "Central Bengaluru",
                "locality": "MG Road Area",
                "subdistrict": "Bengaluru North",
                "district": "Bengaluru Urban",
                "city": "Bengaluru",
                "state": "Karnataka",
                "pincode": "560001",
                "landmark": "Metro station",
                "country": "India",
                "country_code": "in",
                "latitude": "12.971600",
                "longitude": "77.594600",
                "geocoding_place_id": "123",
                "geocoding_osm_type": "way",
                "geocoding_osm_id": "456",
                "geocoding_display_name": "42 MG Road, Bengaluru",
                "geocoding_payload": json.dumps({"place_id": 123, "address": {"road": "MG Road"}}),
                "location_source": Address.LocationSource.GEOLOCATION,
                "address_type": Address.AddressType.WORK,
                "is_default": "on",
            },
        )

        created = Address.objects.filter(user=self.customer, district="Bengaluru Urban").get()
        self.assertRedirects(response, reverse("accounts:address_list"))
        self.assertEqual(created.geocoding_payload["place_id"], 123)
        self.assertEqual(created.road, "MG Road")

    def test_business_registration_creates_license_review_record(self):
        applicant = User.objects.create_user(
            username="manufacturer_applicant",
            email="manufacturer.applicant@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=applicant, role=UserProfile.Role.MANUFACTURER)
        self.client.login(username="manufacturer_applicant", password="Testpass123!")

        response = self.client.post(
            reverse("vendors:vendor_register"),
            {
                "business_name": "Precision Devices India",
                "owner_name": "Anil Rao",
                "email": "precision.devices@gmail.com",
                "phone": "9888888888",
                "address": "12 Industrial Estate, Bengaluru",
                "gst_number": "29ABCDE1234F1Z5",
                "license_number": "MD-TEST-1001",
                "business_type": Vendor.BusinessType.MANUFACTURER,
                "license_type": BusinessLicense.LicenseType.DEVICE_MANUFACTURING,
                "license_form_number": "MD-5",
                "license_legal_name": "Precision Devices India",
                "license_state": "Karnataka",
                "bank_name": "Example Bank",
                "bank_account_number": "1234567890",
                "ifsc_code": "EXAM0001234",
            },
        )

        vendor = Vendor.objects.get(user=applicant)
        license_record = vendor.licenses.get()
        self.assertRedirects(response, reverse("vendors:vendor_dashboard"))
        self.assertEqual(license_record.status, BusinessLicense.Status.PENDING)
        self.assertEqual(license_record.form_number, "MD-5")

    @override_settings(LICENSE_VERIFICATION_API_URL="")
    def test_license_lookup_falls_back_to_official_registry(self):
        license_record = BusinessLicense.objects.create(
            vendor=self.vendor,
            license_type=BusinessLicense.LicenseType.DEVICE_SALE,
            license_number="MD-42-TEST",
        )
        self.client.login(username="vendor", password="Testpass123!")

        response = self.client.post(
            reverse("vendors:business_license_lookup", args=[license_record.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertIn("cdscomdonline.gov.in", response.json()["official_url"])

    def test_regulated_offer_requires_compatible_verified_license(self):
        self.product.requires_business_license = True
        self.product.required_license_type = Product.RegulationType.MEDICAL_DEVICE_SALE
        self.product.save(update_fields=["requires_business_license", "required_license_type"])
        self.offer.is_approved = False
        self.offer.save(update_fields=["is_approved"])
        self.client.login(username="staff", password="Testpass123!")

        blocked = self.client.post(
            reverse("dashboards:review_offer", args=[self.offer.pk]),
            {"decision": "approve"},
        )
        self.offer.refresh_from_db()
        self.assertRedirects(blocked, reverse("dashboards:admin_dashboard"))
        self.assertFalse(self.offer.is_approved)

        BusinessLicense.objects.create(
            vendor=self.vendor,
            license_type=BusinessLicense.LicenseType.DEVICE_MANUFACTURING,
            license_number="MD-5-VERIFIED",
            status=BusinessLicense.Status.VERIFIED,
            valid_until=timezone.localdate() + timedelta(days=365),
        )
        approved = self.client.post(
            reverse("dashboards:review_offer", args=[self.offer.pk]),
            {"decision": "approve"},
        )
        self.offer.refresh_from_db()
        self.assertRedirects(approved, reverse("dashboards:admin_dashboard"))
        self.assertTrue(self.offer.is_approved)

    def test_compliance_role_can_review_license_without_global_staff_flag(self):
        officer = User.objects.create_user(
            username="compliance",
            email="compliance@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=officer, role=UserProfile.Role.COMPLIANCE_OFFICER)
        license_record = BusinessLicense.objects.create(
            vendor=self.vendor,
            license_type=BusinessLicense.LicenseType.DEVICE_SALE,
            license_number="MD-42-REVIEW",
            status=BusinessLicense.Status.MANUAL_REVIEW,
            valid_until=timezone.localdate() + timedelta(days=365),
            document=SimpleUploadedFile("licence.pdf", b"%PDF-1.4\n", content_type="application/pdf"),
        )
        self.client.login(username="compliance", password="Testpass123!")

        dashboard_response = self.client.get(reverse("dashboards:admin_dashboard"))
        review_response = self.client.post(
            reverse("dashboards:review_business_license", args=[license_record.pk]),
            {"decision": "approve", "notes": "Matched against the official record."},
        )

        license_record.refresh_from_db()
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertRedirects(review_response, reverse("dashboards:admin_dashboard"))
        self.assertEqual(license_record.status, BusinessLicense.Status.VERIFIED)
        self.assertEqual(license_record.reviewed_by, officer)

    def test_compliance_dashboard_renders_license_queue_without_django_admin_access(self):
        officer = User.objects.create_user(
            username="compliance_queue",
            email="compliance.queue@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=officer, role=UserProfile.Role.COMPLIANCE_OFFICER)
        BusinessLicense.objects.create(
            vendor=self.vendor,
            license_type=BusinessLicense.LicenseType.DEVICE_SALE,
            license_number="MD-42-VISIBLE",
            status=BusinessLicense.Status.MANUAL_REVIEW,
        )
        self.client.login(username="compliance_queue", password="Testpass123!")

        response = self.client.get(reverse("dashboards:admin_dashboard"))

        self.assertContains(response, "MD-42-VISIBLE")
        self.assertNotContains(response, "Advanced administration")

    def test_support_role_can_reply_without_global_staff_access(self):
        support_user = User.objects.create_user(
            username="support_agent",
            email="support.agent@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=support_user, role=UserProfile.Role.SUPPORT_STAFF)
        ticket = SupportTicket.objects.create(
            user=self.customer,
            subject="Order status question",
            message="Please help with this order.",
        )
        self.client.login(username="support_agent", password="Testpass123!")

        list_response = self.client.get(reverse("extras:support_ticket_list"))
        reply_response = self.client.post(
            reverse("extras:support_ticket_detail", args=[ticket.pk]),
            {"message": "We are checking this for you."},
        )

        ticket.refresh_from_db()
        reply = SupportMessage.objects.get(ticket=ticket, sender=support_user)
        self.assertContains(list_response, "Order status question")
        self.assertRedirects(reply_response, reverse("extras:support_ticket_detail", args=[ticket.pk]))
        self.assertTrue(reply.is_staff_reply)
        self.assertEqual(ticket.status, SupportTicket.Status.IN_PROGRESS)

    def test_customer_and_professional_registration_are_separate(self):
        customer_page = self.client.get(reverse("accounts:register"))
        professional_page = self.client.get(reverse("accounts:professional_register"))

        self.assertContains(customer_page, "Customer registration")
        self.assertNotContains(customer_page, "Professional role")
        self.assertContains(professional_page, "Professional registration")
        self.assertContains(professional_page, "Equipment manufacturer")

    def test_customer_registration_assigns_customer_role(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "new_customer",
                "first_name": "Neha",
                "last_name": "Rao",
                "email": "neha.rao@gmail.com",
                "phone_number": "9876543210",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        created = User.objects.get(username="new_customer")
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertEqual(created.profile.role, UserProfile.Role.CUSTOMER)

    def test_address_form_prefills_account_contact(self):
        self.customer.first_name = "MediMart"
        self.customer.last_name = "Customer"
        self.customer.save(update_fields=["first_name", "last_name"])
        self.customer.profile.phone_number = "9988776655"
        self.customer.profile.save(update_fields=["phone_number"])
        self.client.login(username="customer", password="Testpass123!")

        response = self.client.get(reverse("accounts:address_create"))

        self.assertEqual(response.context["form"].initial["full_name"], "MediMart Customer")
        self.assertEqual(response.context["form"].initial["phone"], "9988776655")

    def test_default_and_custom_admin_panels_are_both_available(self):
        self.client.login(username="staff", password="Testpass123!")

        django_admin_response = self.client.get("/admin/")
        operations_response = self.client.get(reverse("dashboards:admin_dashboard"))

        self.assertEqual(django_admin_response.status_code, 200)
        self.assertContains(django_admin_response, "Django administration")
        self.assertEqual(operations_response.status_code, 200)
        self.assertContains(operations_response, "Operations Center")

    def test_catalog_manager_has_scoped_custom_management_access(self):
        manager = User.objects.create_user(
            username="catalog_manager",
            email="catalog.manager@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=manager, role=UserProfile.Role.CATALOG_MANAGER)
        self.client.login(username="catalog_manager", password="Testpass123!")

        products_response = self.client.get(
            reverse("dashboards:management_records", args=["products"])
        )
        users_response = self.client.get(
            reverse("dashboards:management_records", args=["users"])
        )

        self.assertEqual(products_response.status_code, 200)
        self.assertEqual(users_response.status_code, 403)
        self.assertContains(products_response, self.product.name)

    def test_custom_user_editor_updates_account_and_role(self):
        self.client.login(username="staff", password="Testpass123!")

        response = self.client.post(
            reverse("dashboards:management_edit", args=["users", self.customer.pk]),
            {
                "first_name": "Updated",
                "last_name": "Customer",
                "email": "updated.customer@gmail.com",
                "role": UserProfile.Role.SUPPORT_STAFF,
            },
        )

        self.customer.refresh_from_db()
        self.customer.profile.refresh_from_db()
        self.assertRedirects(
            response,
            reverse("dashboards:management_records", args=["users"]),
        )
        self.assertEqual(self.customer.email, "updated.customer@gmail.com")
        self.assertEqual(self.customer.profile.role, UserProfile.Role.SUPPORT_STAFF)

    def test_catalog_manager_can_manage_health_guide_categories(self):
        manager = User.objects.create_user(
            username="guide_manager",
            email="guide.manager@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=manager, role=UserProfile.Role.CATALOG_MANAGER)
        self.client.login(username="guide_manager", password="Testpass123!")

        create_response = self.client.post(
            reverse("dashboards:management_create", args=["blog_categories"]),
            {"name": "Preventive Care", "description": "Everyday prevention guidance."},
        )
        list_response = self.client.get(
            reverse("dashboards:management_records", args=["blog_categories"])
        )

        self.assertRedirects(
            create_response,
            reverse("dashboards:management_records", args=["blog_categories"]),
        )
        self.assertTrue(BlogCategory.objects.filter(name="Preventive Care").exists())
        self.assertContains(list_response, "Preventive Care")

    def test_blog_search_and_product_catalog_layout(self):
        BlogPost.objects.create(
            title="Managing blood pressure safely",
            slug="managing-blood-pressure-safely",
            excerpt="A practical home monitoring guide.",
            content="Measure at the same time each day and follow clinical advice.",
            status=BlogPost.Status.PUBLISHED,
            published_at=timezone.now(),
        )

        blog_response = self.client.get(reverse("extras:blog_list"), {"q": "blood pressure"})
        product_response = self.client.get(reverse("products:product_list"))

        self.assertContains(blog_response, "Managing blood pressure safely")
        self.assertContains(blog_response, "blog-search")
        self.assertContains(product_response, "catalog-product-grid")

    def create_order(self, status):
        order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            address_snapshot="MediMart Customer\nTest Street",
            subtotal=Decimal("1450.00"),
            discount=Decimal("0.00"),
            delivery_charge=Decimal("49.00"),
            total_amount=Decimal("1499.00"),
            payment_method=Order.PaymentMethod.COD,
            order_status=status,
        )
        OrderItem.objects.create(
            order=order,
            vendor_product=self.offer,
            vendor=self.vendor,
            product=self.product,
            product_name=self.product.name,
            seller_name=self.vendor.business_name,
            sku=self.product.sku,
            quantity=1,
            unit_price=self.offer.price,
            total_price=self.offer.price,
        )
        return order
