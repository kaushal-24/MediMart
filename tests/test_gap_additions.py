from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from extras.models import Notification
from products.models import Category, PriceAlert, Product, ProductClinicalProfile


class GapAdditionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="price-alert-user",
            email="price-alert-user@gmail.com",
            password="test-password",
        )
        self.category = Category.objects.create(name="Gap Test Category")
        self.product = Product.objects.create(
            name="Gap Test Monitor",
            sku="GAP-TEST-001",
            category=self.category,
            product_type=Product.ProductType.MEDICAL_EQUIPMENT,
            description="A test product for marketplace alerts.",
            mrp=Decimal("1000.00"),
            selling_price=Decimal("800.00"),
        )

    def test_search_suggestions_expose_entity_groups_and_recent_searches(self):
        session = self.client.session
        session["recent_search_queries"] = ["blood pressure"]
        session.save()

        response = self.client.get(reverse("products:search_suggestions"), {"q": "gap"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("categories", response.json())
        self.assertIn("brands", response.json())
        self.assertIn("lab_tests", response.json())
        self.assertEqual(response.json()["recent_queries"], ["blood pressure"])

    def test_customer_can_create_price_alert(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("products:price_alert_create", args=[self.product.pk]),
            {"target_price": "700.00"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PriceAlert.objects.filter(user=self.user, product=self.product, is_active=True).exists())

    def test_price_drop_notifies_and_closes_matching_alert(self):
        PriceAlert.objects.create(user=self.user, product=self.product, target_price=Decimal("700.00"))

        self.product.selling_price = Decimal("650.00")
        self.product.save(update_fields={"selling_price"})

        alert = PriceAlert.objects.get(user=self.user, product=self.product)
        self.assertFalse(alert.is_active)
        self.assertTrue(alert.notified_at)
        self.assertTrue(Notification.objects.filter(user=self.user, title="Price drop alert").exists())

    def test_reviewed_dosage_information_is_visible_on_product_detail(self):
        ProductClinicalProfile.objects.create(
            product=self.product,
            dosage_information="Use only as directed on the prescription.",
            onset_information="Typically within 30 minutes.",
            duration_information="Follow the prescribed schedule.",
            quick_tips="Take with water unless your clinician advises otherwise.",
            severity_level=ProductClinicalProfile.SeverityLevel.IMPORTANT,
            review_status=ProductClinicalProfile.ReviewStatus.PUBLISHED,
        )

        response = self.client.get(reverse("products:product_detail", args=[self.product.slug]))

        self.assertContains(response, "Dosage information")
        self.assertContains(response, "Typically within 30 minutes.")
        self.assertContains(response, "Important precautions")
