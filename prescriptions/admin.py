from django.contrib import admin
from django.utils import timezone

from .models import Prescription, PrescriptionItem, PrescriptionReview


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 1


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "patient_name",
        "doctor_name",
        "prescription_date",
        "status",
        "scan_status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status", "scan_status", "customer_consent", "created_at", "prescription_date")
    search_fields = (
        "user__username",
        "user__email",
        "patient_name",
        "doctor_name",
        "doctor_registration_number",
        "requested_medicines",
        "notes",
    )
    readonly_fields = ("created_at", "updated_at", "reviewed_at", "scan_completed_at", "scan_summary", "scan_flags")
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


@admin.register(PrescriptionReview)
class PrescriptionReviewAdmin(admin.ModelAdmin):
    list_display = ("prescription", "reviewer", "decision", "pharmacy_license_number", "created_at")
    list_filter = ("decision", "created_at")
    search_fields = ("prescription__patient_name", "prescription__user__username", "reviewer__username", "pharmacy_license_number")
    readonly_fields = ("prescription", "reviewer", "decision", "pharmacy_license_number", "notes", "validation_snapshot", "created_at")
