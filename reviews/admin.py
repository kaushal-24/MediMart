from django.contrib import admin
from django.utils import timezone

from .models import Review, ReviewAbuseReport, ReviewHelpfulVote, ReviewSellerReply


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "title", "is_approved", "created_at")
    list_filter = ("rating", "is_approved", "created_at")
    search_fields = ("product__name", "user__username", "title", "comment")
    readonly_fields = ("created_at", "updated_at")
    actions = ("approve_reviews", "unapprove_reviews")

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)

    @admin.action(description="Unapprove selected reviews")
    def unapprove_reviews(self, request, queryset):
        queryset.update(is_approved=False)


@admin.register(ReviewHelpfulVote)
class ReviewHelpfulVoteAdmin(admin.ModelAdmin):
    list_display = ("review", "user", "is_helpful", "created_at")
    list_filter = ("is_helpful", "created_at")
    search_fields = ("review__product__name", "user__username")
    readonly_fields = ("created_at",)


@admin.register(ReviewAbuseReport)
class ReviewAbuseReportAdmin(admin.ModelAdmin):
    list_display = ("review", "user", "reason", "status", "reviewed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("review__product__name", "user__username", "reason")
    readonly_fields = ("created_at",)
    actions = ("mark_reviewed", "reject_reports")

    @admin.action(description="Mark selected reports reviewed")
    def mark_reviewed(self, request, queryset):
        queryset.update(status=ReviewAbuseReport.Status.REVIEWED, reviewed_by=request.user, reviewed_at=timezone.now())

    @admin.action(description="Reject selected reports")
    def reject_reports(self, request, queryset):
        queryset.update(status=ReviewAbuseReport.Status.REJECTED, reviewed_by=request.user, reviewed_at=timezone.now())


@admin.register(ReviewSellerReply)
class ReviewSellerReplyAdmin(admin.ModelAdmin):
    list_display = ("review", "seller", "is_published", "created_at", "updated_at")
    list_filter = ("is_published", "created_at")
    search_fields = ("review__product__name", "seller__username", "reply")
    readonly_fields = ("created_at", "updated_at")
