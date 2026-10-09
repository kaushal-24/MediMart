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
    list_display = ("title", "category", "author", "status", "published_at")
    list_filter = ("status", "category", "published_at")
    search_fields = ("title", "excerpt", "content")
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
