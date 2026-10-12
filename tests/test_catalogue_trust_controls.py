from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product, ProductQuestion, ProductSubstitute, ProductVariant
from reviews.models import Review, ReviewAbuseReport, ReviewHelpfulVote


class CatalogueTrustControlTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="catalogue-customer",
            email="catalogue-customer@gmail.com",
            password="Testpass123!",
        )
        self.category = Category.objects.create(name="Catalogue tests")
        self.product = Product.objects.create(
            name="Catalogue Test Product",
            sku="CAT-001",
            category=self.category,
            product_type=Product.ProductType.HEALTHCARE_PRODUCT,
            description="Test product.",
            mrp=Decimal("100.00"),
            selling_price=Decimal("80.00"),
            is_active=True,
        )

    def test_approved_variant_is_visible_on_product_page(self):
        ProductVariant.objects.create(
            product=self.product,
            sku="CAT-001-10",
            pack_size="10 tablets",
            strength="500 mg",
            mrp=Decimal("90.00"),
            selling_price=Decimal("75.00"),
            is_approved=True,
        )

        response = self.client.get(self.product.get_absolute_url())

        self.assertContains(response, "Available variants")
        self.assertContains(response, "10 tablets")

    def test_customer_question_enters_moderation_queue(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("products:product_question_create", args=[self.product.pk]),
            {"question": "Is this suitable for daily use?"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        question = ProductQuestion.objects.get(product=self.product, user=self.user)
        self.assertEqual(question.status, ProductQuestion.Status.PENDING)

    def test_helpful_vote_and_abuse_report_are_unique_per_user(self):
        review = Review.objects.create(
            user=self.user,
            product=self.product,
            rating=5,
            title="Good product",
            comment="Works as described.",
            is_approved=True,
        )
        self.client.force_login(self.user)

        vote_url = reverse("reviews:helpful_vote", args=[review.pk])
        self.assertEqual(self.client.post(vote_url, {"is_helpful": "true"}).status_code, 200)
        self.assertEqual(self.client.post(vote_url, {"is_helpful": "false"}).status_code, 200)
        self.assertEqual(ReviewHelpfulVote.objects.filter(review=review, user=self.user).count(), 1)
        self.assertFalse(ReviewHelpfulVote.objects.get(review=review, user=self.user).is_helpful)

        report_url = reverse("reviews:abuse_report", args=[review.pk])
        self.assertEqual(self.client.post(report_url, {"reason": "This looks misleading"}).status_code, 200)
        self.assertEqual(self.client.post(report_url, {"reason": "Duplicate report"}).status_code, 200)
        self.assertEqual(ReviewAbuseReport.objects.filter(review=review, user=self.user).count(), 1)

    def test_substitute_cannot_point_to_itself(self):
        substitute = ProductSubstitute(product=self.product, substitute=self.product)
        with self.assertRaises(Exception):
            substitute.full_clean()
