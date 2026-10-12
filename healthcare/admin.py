from django.contrib import admin

from .models import (
    Consultation,
    ConsultationMessage,
    Dependent,
    HealthRecord,
    HealthRecordShare,
    LabBooking,
    LabPartner,
    LabTest,
    LabBranch,
    LabCollectionSlot,
    LabSampleEvent,
    LabReportValue,
    LabReferenceRange,
    LabInvoice,
    LabRefund,
    LabSettlement,
    LabDispute,
    DoctorAvailability,
    ConsultationPayment,
    ConsultationFollowUp,
    MedicationReminder,
)


@admin.register(Dependent)
class DependentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "relationship", "date_of_birth", "is_active")
    list_filter = ("relationship", "gender", "is_active")
    search_fields = ("full_name", "user__username", "user__email")


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "dependent", "record_type", "record_date", "is_archived")
    list_filter = ("record_type", "is_archived", "created_at")
    search_fields = ("title", "provider_name", "user__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(HealthRecordShare)
class HealthRecordShareAdmin(admin.ModelAdmin):
    list_display = ("record", "shared_with", "purpose", "granted_at", "expires_at", "revoked_at")
    list_filter = ("granted_at", "expires_at", "revoked_at")
    search_fields = ("record__title", "shared_with__username", "purpose")


@admin.register(LabPartner)
class LabPartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "accreditations", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name", "city", "address")


@admin.register(LabBranch)
class LabBranchAdmin(admin.ModelAdmin):
    list_display = ("name", "partner", "city", "pincode", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name", "partner__name", "city", "pincode")


@admin.register(LabCollectionSlot)
class LabCollectionSlotAdmin(admin.ModelAdmin):
    list_display = ("partner", "starts_at", "ends_at", "capacity", "booked_count", "is_blackout", "is_active")
    list_filter = ("is_blackout", "is_active", "starts_at")


@admin.register(LabSampleEvent)
class LabSampleEventAdmin(admin.ModelAdmin):
    list_display = ("booking", "event_type", "barcode", "location", "recorded_by", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("booking__accession_number", "barcode", "location")
    readonly_fields = ("created_at",)


@admin.register(LabReportValue)
class LabReportValueAdmin(admin.ModelAdmin):
    list_display = ("booking", "test_name", "value", "unit", "reference_range", "abnormal_flag", "medically_reviewed", "explanation_reviewed_by")
    list_filter = ("medically_reviewed", "abnormal_flag")
    search_fields = ("booking__accession_number", "test_name")


@admin.register(LabReferenceRange)
class LabReferenceRangeAdmin(admin.ModelAdmin):
    list_display = ("lab_test", "test_name", "sex", "min_age_years", "max_age_years", "range_text", "is_active")
    list_filter = ("sex", "is_active", "lab_test__partner")
    search_fields = ("lab_test__name", "test_name", "range_text")


@admin.register(LabInvoice)
class LabInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "booking", "total_amount", "status", "issued_at", "paid_at")
    list_filter = ("status", "issued_at")
    search_fields = ("invoice_number", "booking__accession_number", "booking__user__username")
    readonly_fields = ("invoice_number", "issued_at")


@admin.register(LabRefund)
class LabRefundAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "status", "reason", "reviewed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("invoice__invoice_number", "reason")


@admin.register(LabSettlement)
class LabSettlementAdmin(admin.ModelAdmin):
    list_display = ("partner", "period_start", "period_end", "gross_amount", "net_amount", "status")
    list_filter = ("status", "partner")
    search_fields = ("partner__name", "reference")


@admin.register(LabDispute)
class LabDisputeAdmin(admin.ModelAdmin):
    list_display = ("booking", "raised_by", "category", "status", "created_at", "resolved_by")
    list_filter = ("status", "category", "created_at")
    search_fields = ("booking__accession_number", "raised_by__username", "description")


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = ("name", "partner", "category", "price", "report_sla_hours", "is_home_collection", "has_image", "is_active")
    list_filter = ("category", "is_home_collection", "is_active", "partner")
    search_fields = ("name", "description", "partner__name")

    @admin.display(boolean=True, description="Image")
    def has_image(self, obj):
        return bool(obj.image)


@admin.register(LabBooking)
class LabBookingAdmin(admin.ModelAdmin):
    list_display = ("lab_test", "user", "dependent", "status", "scheduled_start", "report_ready_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "lab_test__name", "accession_number")
    readonly_fields = ("created_at", "updated_at")


class ConsultationMessageInline(admin.TabularInline):
    model = ConsultationMessage
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "doctor", "mode", "status", "fee", "scheduled_at")
    list_filter = ("mode", "status", "created_at")
    search_fields = ("user__username", "doctor__full_name", "symptoms")
    readonly_fields = ("created_at", "updated_at")
    inlines = (ConsultationMessageInline,)


@admin.register(ConsultationMessage)
class ConsultationMessageAdmin(admin.ModelAdmin):
    list_display = ("consultation", "sender", "created_at")
    search_fields = ("consultation__user__username", "sender__username", "message")
    readonly_fields = ("created_at",)


@admin.register(DoctorAvailability)
class DoctorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("doctor", "weekday", "start_time", "end_time", "slot_minutes", "capacity", "is_active")
    list_filter = ("weekday", "is_active")
    search_fields = ("doctor__full_name", "doctor__registration_number")


@admin.register(ConsultationPayment)
class ConsultationPaymentAdmin(admin.ModelAdmin):
    list_display = ("consultation", "amount", "status", "provider", "provider_payment_id", "paid_at")
    list_filter = ("status", "provider")
    search_fields = ("consultation__user__username", "consultation__doctor__full_name", "provider_payment_id")


@admin.register(ConsultationFollowUp)
class ConsultationFollowUpAdmin(admin.ModelAdmin):
    list_display = ("consultation", "scheduled_at", "status", "created_by", "created_at")
    list_filter = ("status", "scheduled_at")
    search_fields = ("consultation__user__username", "consultation__doctor__full_name", "notes")


@admin.register(MedicationReminder)
class MedicationReminderAdmin(admin.ModelAdmin):
    list_display = ("label", "user", "dependent", "frequency", "next_due_at", "is_active")
    list_filter = ("is_active", "next_due_at")
    search_fields = ("label", "user__username", "product__name")


