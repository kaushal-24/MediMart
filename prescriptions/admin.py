from django.contrib import admin
from django.utils import timezone

from .models import Prescription, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 1


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "doctor_name",
        "prescription_date",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status", "created_at", "prescription_date")
    search_fields = ("user__username", "user__email", "doctor_name", "notes")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
    actions = ("mark_under_review", "approve_prescriptions", "reject_prescriptions")
    inlines = (PrescriptionItemInline,)

    @admin.action(description="Mark selected prescriptions under review")
    def mark_under_review(self, request, queryset):
        queryset.update(status=Prescription.Status.UNDER_REVIEW)

    @admin.action(description="Approve selected prescriptions")
    def approve_prescriptions(self, request, queryset):
        approved = 0
        for prescription in queryset.prefetch_related("items"):
            if not prescription.valid_until or prescription.valid_until < timezone.localdate():
                continue
            if not prescription.items.exists():
                continue
            prescription.mark_approved(request.user)
            approved += 1
        self.message_user(
            request,
            f"Approved {approved} prescription(s). Expired or unscoped records were skipped.",
        )

    @admin.action(description="Reject selected prescriptions")
    def reject_prescriptions(self, request, queryset):
        queryset.update(
            status=Prescription.Status.REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
