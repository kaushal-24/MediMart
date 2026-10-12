from django.contrib import admin
from django.utils import timezone

from .models import (
    BlogCategory,
    BlogPost,
    DoctorProfile,
    Notification,
    NotificationDelivery,
    SupportMessage,
    SupportTicket,
    ContentIssue,
    PharmacistProfile,
    QualityComplaint,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "user__username")


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("notification", "channel", "destination", "status", "attempts", "next_attempt_at")
    list_filter = ("channel", "status", "created_at")
    search_fields = ("destination", "notification__title", "notification__user__username")
    readonly_fields = ("notification", "channel", "destination", "attempts", "sent_at", "last_error", "provider_reference", "created_at", "updated_at")


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "user", "category", "status", "updated_at")
    list_filter = ("category", "status", "created_at")
    search_fields = ("subject", "message", "order_number", "user__username")
    readonly_fields = ("created_at", "updated_at")
    inlines = (SupportMessageInline,)
    actions = ("mark_in_progress", "mark_resolved", "mark_closed")

    @admin.action(description="Mark selected tickets in progress")
    def mark_in_progress(self, request, queryset):
        queryset.update(status=SupportTicket.Status.IN_PROGRESS)

    @admin.action(description="Mark selected tickets resolved")
    def mark_resolved(self, request, queryset):
        queryset.update(status=SupportTicket.Status.RESOLVED)

    @admin.action(description="Mark selected tickets closed")
    def mark_closed(self, request, queryset):
        queryset.update(status=SupportTicket.Status.CLOSED)


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("ticket", "sender", "is_staff_reply", "created_at")
    list_filter = ("is_staff_reply", "created_at")
    search_fields = ("ticket__subject", "sender__username", "message")


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "author",
        "status",
        "reviewer_name",
        "last_reviewed_at",
        "review_due_at",
        "published_at",
    )
    list_filter = ("status", "category", "published_at")
    search_fields = ("title", "excerpt", "content", "reviewer_name", "source_references")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    actions = ("publish_posts", "draft_posts")

    @admin.action(description="Publish selected posts")
    def publish_posts(self, request, queryset):
        for post in queryset:
            post.status = BlogPost.Status.PUBLISHED
            post.save(update_fields=["status", "published_at", "updated_at"])

    @admin.action(description="Move selected posts to draft")
    def draft_posts(self, request, queryset):
        queryset.update(status=BlogPost.Status.DRAFT)


@admin.register(ContentIssue)
class ContentIssueAdmin(admin.ModelAdmin):
    list_display = ("__str__", "issue_type", "status", "reporter", "reviewed_by", "created_at")
    list_filter = ("issue_type", "status", "created_at")
    search_fields = ("details", "reviewer_note", "blog_post__title", "product__name", "reporter__username")
    readonly_fields = ("created_at", "updated_at")
    actions = ("mark_in_review", "mark_resolved", "mark_dismissed")

    @admin.action(description="Move selected issues to review")
    def mark_in_review(self, request, queryset):
        queryset.update(status=ContentIssue.Status.IN_REVIEW, reviewed_by=request.user)

    @admin.action(description="Resolve selected issues")
    def mark_resolved(self, request, queryset):
        queryset.update(status=ContentIssue.Status.RESOLVED, reviewed_by=request.user)

    @admin.action(description="Dismiss selected issues")
    def mark_dismissed(self, request, queryset):
        queryset.update(status=ContentIssue.Status.DISMISSED, reviewed_by=request.user)


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "user",
        "specialization",
        "experience_years",
        "consultation_fee",
        "is_verified",
    )
    list_filter = ("is_verified", "specialization")
    search_fields = ("full_name", "specialization", "clinic_name", "user__username")
    readonly_fields = ("created_at", "updated_at")
    actions = ("verify_doctors", "unverify_doctors")

    @admin.action(description="Verify selected doctors")
    def verify_doctors(self, request, queryset):
        verified = 0
        for doctor in queryset:
            if not all(
                [
                    doctor.registration_number,
                    doctor.medical_council,
                    doctor.qualification,
                    doctor.qualification_document,
                ]
            ):
                continue
            doctor.is_verified = True
            doctor.verified_by = request.user
            doctor.verified_at = timezone.now()
            doctor.save(update_fields=["is_verified", "verified_by", "verified_at", "updated_at"])
            verified += 1
        self.message_user(request, f"Verified {verified} doctor(s) with complete credentials.")

    @admin.action(description="Unverify selected doctors")
    def unverify_doctors(self, request, queryset):
        queryset.update(is_verified=False, verified_by=None, verified_at=None)


@admin.register(PharmacistProfile)
class PharmacistProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "registration_number", "pharmacy_name", "state", "is_verified")
    list_filter = ("is_verified", "state")
    search_fields = ("full_name", "registration_number", "pharmacy_name", "pharmacy_license_number", "user__username")
    readonly_fields = ("created_at", "updated_at", "verified_by", "verified_at")
    actions = ("verify_pharmacists", "unverify_pharmacists")

    @admin.action(description="Verify selected pharmacists")
    def verify_pharmacists(self, request, queryset):
        updated = queryset.filter(registration_number__gt="", pharmacy_license_number__gt="").update(
            is_verified=True, verified_by=request.user, verified_at=timezone.now()
        )
        self.message_user(request, f"Verified {updated} pharmacist(s) with licence details.")

    @admin.action(description="Remove pharmacist verification")
    def unverify_pharmacists(self, request, queryset):
        queryset.update(is_verified=False, verified_by=None, verified_at=None)


@admin.register(QualityComplaint)
class QualityComplaintAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "user", "batch_number", "status", "reviewed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("product__name", "user__username", "batch_number", "description", "resolution_note")
    readonly_fields = ("created_at", "updated_at")
    actions = ("mark_under_review", "mark_escalated", "mark_resolved")

    @admin.action(description="Move complaints to review")
    def mark_under_review(self, request, queryset):
        queryset.update(status=QualityComplaint.Status.UNDER_REVIEW, reviewed_by=request.user)

    @admin.action(description="Escalate selected complaints")
    def mark_escalated(self, request, queryset):
        queryset.update(status=QualityComplaint.Status.ESCALATED, reviewed_by=request.user)

    @admin.action(description="Resolve selected complaints")
    def mark_resolved(self, request, queryset):
        queryset.update(status=QualityComplaint.Status.RESOLVED, reviewed_by=request.user)
