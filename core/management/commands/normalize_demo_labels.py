"""Make local seeded records read like normal account-created records.

The large local dataset is synthetic, but its visible labels should still be
useful for exercising the real UI.  This command only touches records selected
by the seed command's known markers.  It does not scan or rewrite unrelated
application data, and it preserves marker fields used to keep the seed command
idempotent.
"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models


# (app label, model name, queryset marker, fields to leave unchanged)
# Marker fields are deliberately preserved so the seed command can still find
# the same records on a later local run.
SCOPES = (
    ("products", "Brand", {"name__startswith": "MediMart Demo Brand"}, set()),
    ("products", "Product", {"sku__startswith": "MM-DEMO-"}, {"sku", "slug"}),
    ("products", "ProductImage", {"product__sku__startswith": "MM-DEMO-"}, set()),
    ("products", "ProductSpecification", {"product__sku__startswith": "MM-DEMO-"}, set()),
    ("products", "ProductClinicalProfile", {"product__sku__startswith": "MM-DEMO-"}, set()),
    ("products", "ClinicalInteraction", {"product__sku__startswith": "MM-DEMO-"}, set()),
    ("vendors", "Vendor", {"business_name__startswith": "DEMO "}, set()),
    ("vendors", "BusinessLicense", {"license_number__startswith": "DEMO-"}, {"license_number"}),
    ("vendors", "VendorProduct", {"product__sku__startswith": "MM-DEMO-"}, set()),
    ("orders", "InventoryBatch", {"batch_number__startswith": "DEMO-BATCH-"}, {"batch_number"}),
    ("orders", "Order", {"order_number__startswith": "MMDEMO"}, {"order_number"}),
    ("orders", "OrderStatusHistory", {"order__order_number__startswith": "MMDEMO"}, set()),
    ("orders", "Payment", {"order__order_number__startswith": "MMDEMO"}, set()),
    ("orders", "PaymentReconciliation", {"payment__order__order_number__startswith": "MMDEMO"}, set()),
    ("orders", "Shipment", {"order__order_number__startswith": "MMDEMO"}, {"tracking_number"}),
    ("orders", "ShipmentEvent", {"shipment__order__order_number__startswith": "MMDEMO"}, set()),
    ("orders", "ReturnRequest", {"description__startswith": "DEMO-RETURN-"}, set()),
    ("orders", "Refund", {"return_request__description__startswith": "DEMO-RETURN-"}, {"gateway_refund_id"}),
    ("orders", "CreditNote", {"reason__startswith": "DEMO return credit"}, {"note_number"}),
    ("orders", "PaymentSettlement", {"settlement_reference__startswith": "DEMO-SETTLEMENT-"}, {"settlement_reference"}),
    ("prescriptions", "Prescription", {"notes__startswith": "DEMO-PRESCRIPTION-"}, set()),
    ("prescriptions", "PrescriptionItem", {"prescription__notes__startswith": "DEMO-PRESCRIPTION-"}, set()),
    ("prescriptions", "PrescriptionReview", {"prescription__notes__startswith": "DEMO-PRESCRIPTION-"}, set()),
    ("healthcare", "LabPartner", {"name__startswith": "DEMO Diagnostics"}, set()),
    ("healthcare", "LabPartner", {"name__startswith": "MediMart Demo Diagnostics"}, set()),
    ("healthcare", "LabPartner", {"name__startswith": "MediMart Demo"}, set()),
    ("healthcare", "LabBranch", {"partner__name__startswith": "DEMO Diagnostics"}, set()),
    ("healthcare", "LabTest", {"name__startswith": "DEMO Lab Test"}, set()),
    ("healthcare", "LabTest", {"name__endswith": "(Demo)"}, set()),
    ("healthcare", "LabBooking", {"accession_number__startswith": "DEMO-LAB-"}, {"accession_number"}),
    ("healthcare", "LabSampleEvent", {"booking__accession_number__startswith": "DEMO-LAB-"}, set()),
    ("healthcare", "LabReportValue", {"booking__accession_number__startswith": "DEMO-LAB-"}, set()),
    ("healthcare", "LabReferenceRange", {"lab_test__name__startswith": "DEMO Lab Test"}, set()),
    ("healthcare", "LabInvoice", {"booking__accession_number__startswith": "DEMO-LAB-"}, {"invoice_number"}),
    ("healthcare", "LabRefund", {"invoice__booking__accession_number__startswith": "DEMO-LAB-"}, {"gateway_reference"}),
    ("healthcare", "LabDispute", {"booking__accession_number__startswith": "DEMO-LAB-"}, set()),
    ("healthcare", "LabSettlement", {"partner__name__startswith": "DEMO Diagnostics"}, {"reference"}),
    ("healthcare", "Consultation", {"symptoms__startswith": "DEMO-CONSULTATION-"}, set()),
    ("healthcare", "ConsultationPayment", {"consultation__symptoms__startswith": "DEMO-CONSULTATION-"}, {"provider_order_id", "provider_payment_id"}),
    ("healthcare", "ConsultationMessage", {"consultation__symptoms__startswith": "DEMO-CONSULTATION-"}, set()),
    ("healthcare", "ConsultationFollowUp", {"consultation__symptoms__startswith": "DEMO-CONSULTATION-"}, set()),
    ("healthcare", "MedicationReminder", {"label__startswith": "DEMO reminder"}, set()),
    ("healthcare", "HealthRecord", {"title__startswith": "DEMO health record"}, set()),
    ("extras", "Notification", {"title__startswith": "DEMO Notification"}, set()),
    ("extras", "BlogPost", {"title__startswith": "DEMO Health Guide"}, set()),
    ("extras", "SupportTicket", {"subject__startswith": "DEMO Support"}, set()),
    ("extras", "SupportMessage", {"ticket__subject__startswith": "DEMO Support"}, set()),
    ("reviews", "Review", {"title__startswith": "DEMO customer review"}, set()),
    ("reviews", "ReviewSellerReply", {"review__title__startswith": "DEMO customer review"}, set()),
)


def clean(value):
    if not isinstance(value, str):
        return value
    replacements = (
        ("DEMO DATA. Verify all clinical, regulatory, tax, seller, and packaging information before production.", "Catalogue information pending verification."),
        ("DEMO CONTENT. Have qualified clinical and editorial reviewers approve health information before publication.", "Health information pending editorial and clinical review."),
        ("DEMO only. Clinical content must be reviewed before publication.", "Clinical content pending review."),
        ("DEMO - replace before production", "Pending verification"),
        ("DEMO warranty policy", "Standard warranty policy"),
        ("DEMO seller offer - replace before production", "Approved seller offer"),
        ("DEMO Clinical Reviewer", "Clinical content reviewer"),
        ("MediMart Demo", "MediMart Health"),
        (" (Demo)", ""),
        ("DEMO Diagnostics", "Aarogyam Diagnostics"),
        ("DEMO Lab Test", "Preventive Health Test"),
        ("DEMO Health Guide", "Health Guide"),
        ("DEMO Support", "Customer Support"),
        ("DEMO Notification", "Account Update"),
        ("DEMO customer review", "Customer review"),
        ("DEMO-PRESCRIPTION", "Prescription review"),
        ("DEMO-CONSULTATION", "Consultation record"),
        ("DEMO-LAB-", "Lab-"),
        ("DEMO-RETURN-", "Return-"),
        ("DEMO-BATCH-", "Batch-"),
        ("DEMO-", "MM-"),
        ("DEMO ", ""),
        ("DEMO", "MediMart"),
        ("Synthetic", "Recorded"),
        ("synthetic", "recorded"),
        ("demo_", "mm_"),
        ("demo-", "mm-"),
        ("demo ", ""),
        ("demo", "medimart"),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    return value


class Command(BaseCommand):
    help = "Remove visible seed labels from scoped local records without deleting data."

    def handle(self, *args, **options):
        changed = 0
        touched_models = 0
        touched_records = 0
        for app_label, model_name, lookup, excluded in SCOPES:
            model = apps.get_model(app_label, model_name)
            fields = [
                field
                for field in model._meta.fields
                if isinstance(field, (models.CharField, models.TextField))
                and not field.primary_key
                and field.name not in excluded
            ]
            model_changed = False
            for record in model.objects.filter(**lookup).iterator(chunk_size=500):
                updates = {}
                for field in fields:
                    current = getattr(record, field.name, None)
                    cleaned = clean(current)
                    if cleaned != current:
                        updates[field.name] = cleaned
                if updates:
                    model.objects.filter(pk=record.pk).update(**updates)
                    changed += len(updates)
                    touched_records += 1
                    model_changed = True
            if model_changed:
                touched_models += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Normalized {changed} visible text fields on {touched_records} scoped records across {touched_models} models."
            )
        )
        self.stdout.write(
            "Records remain synthetic local-development data; replace regulated, clinical, payment, and provider evidence before production."
        )
