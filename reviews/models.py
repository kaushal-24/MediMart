from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from orders.models import OrderItem
from products.models import Product


class Review(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.SET_NULL,
        related_name="reviews",
        blank=True,
        null=True,
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=120)
    comment = models.TextField()
    image = models.ImageField(upload_to="reviews/", blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_user_product_review")
        ]

    def __str__(self):
        return f"{self.product.name} review by {self.user.username}"


class ReviewHelpfulVote(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="helpful_votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_helpful_votes")
    is_helpful = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["review", "user"], name="unique_review_helpful_vote")]


class ReviewAbuseReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        REVIEWED = "reviewed", "Reviewed"
        REJECTED = "rejected", "Rejected"

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="abuse_reports")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_abuse_reports")
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="reviewed_abuse_reports", blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["review", "user"], name="unique_review_abuse_report")]


class ReviewSellerReply(models.Model):
    review = models.OneToOneField(Review, on_delete=models.CASCADE, related_name="seller_reply")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_review_replies")
    reply = models.TextField()
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Seller reply to review #{self.review_id}"
