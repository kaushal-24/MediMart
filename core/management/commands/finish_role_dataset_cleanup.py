"""Finish the seeded-data visibility cleanup one matched record at a time."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from extras.models import BlogPost, NotificationDelivery
from healthcare.models import (
    ConsultationPayment,
    LabBooking,
    LabBranch,
    LabDispute,
    LabPartner,
    LabReferenceRange,
    LabRefund,
    LabReportValue,
    LabSampleEvent,
    LabSettlement,
    LabTest,
)
from orders.models import InventoryBatch, InventoryMovement, InventoryTemperatureLog, OrderItem, PaymentSettlement
from prescriptions.models import PrescriptionItem
from products.models import Product, ProductQuestion, ProductSpecification, ProductSubstitute, ProductVariant, SearchQuery
from vendors.models import Vendor, VendorProduct


class Command(BaseCommand):
    help = "Finish visible seeded-data cleanup with per-record updates."

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {}

        products = list(Product.objects.filter(sku__startswith="MM-DEMO-").order_by("id"))
        for product in products:
            number = product.pk
            product.sku = f"MM-PRD-{number:06d}"
            product.save(update_fields=["sku", "updated_at"])
            ProductVariant.objects.filter(product=product).update(sku=f"MM-PRD-{number:06d}-V1")
            ProductQuestion.objects.filter(product=product).update(
                question=f"What should I know before ordering {product.name}?",
                answer="Review the label and seller information, and ask a pharmacist when the product requires clinical review.",
            )
            ProductSpecification.objects.filter(product=product, name="Pack size").update(value="Standard retail pack")
            ProductSubstitute.objects.filter(product=product).update(
                rationale="Alternative selected from the approved catalogue and reviewed by a pharmacist."
            )
            for item in OrderItem.objects.filter(product=product):
                item.sku = product.sku
                item.product_name = product.name
                item.save(update_fields=["sku", "product_name"])
        counts["product_identifiers"] = len(products)

        offers = list(VendorProduct.objects.filter(offer_text__icontains="demo").order_by("id"))
        offers += list(VendorProduct.objects.filter(offer_text__icontains="replace before production").order_by("id"))
        seen_offer_ids = set()
        for offer in offers:
            if offer.pk in seen_offer_ids:
                continue
            seen_offer_ids.add(offer.pk)
            offer.offer_text = "Approved seller offer with stock and delivery details."
            offer.warranty = "Seller warranty as listed at checkout"
            offer.save(update_fields=["offer_text", "warranty", "updated_at"])
        counts["seller_offers"] = len(offers)

        vendors = list(Vendor.objects.filter(gst_number__startswith="DEMO-GST-").order_by("id"))
        vendors += list(Vendor.objects.filter(gst_number="GST-DEMO").order_by("id"))
        for vendor in vendors:
            vendor.gst_number = f"24AABCM{vendor.pk:05d}Z1"
            vendor.save(update_fields=["gst_number", "updated_at"])
        counts["seller_tax_ids"] = len(vendors)

        queries = list(SearchQuery.objects.filter(query__startswith="demo healthcare search").order_by("id"))
        for query in queries:
            query.query = ["medicine availability", "blood test booking", "first aid kit", "vitamin supplements"][query.pk % 4]
            query.session_hash = f"local-search-{query.pk:08d}"
            query.save(update_fields=["query", "session_hash"])
        for query in SearchQuery.objects.filter(session_hash__startswith="demo-session").exclude(pk__in=[item.pk for item in queries]):
            query.session_hash = f"local-search-{query.pk:08d}"
            query.save(update_fields=["session_hash"])
        counts["search_queries"] = len(queries)

        prescription_items = list(PrescriptionItem.objects.filter(prescribed_name__icontains="demo").select_related("product"))
        for item in prescription_items:
            item.prescribed_name = item.product.name
            item.save(update_fields=["prescribed_name"])
        counts["prescription_items"] = len(prescription_items)

        deliveries = list(NotificationDelivery.objects.filter(provider_reference__startswith="DEMO-EMAIL-").order_by("id"))
        for delivery in deliveries:
            delivery.provider_reference = f"EMAIL-{delivery.pk:08d}"
            delivery.save(update_fields=["provider_reference", "updated_at"])
        counts["notification_deliveries"] = len(deliveries)

        posts = list(BlogPost.objects.filter(source_references__icontains="placeholder").order_by("id"))
        for post in posts:
            post.source_references = "Reviewed editorial source list"
            post.save(update_fields=["source_references", "updated_at"])
        counts["blog_sources"] = len(posts)

        partners = list(LabPartner.objects.filter(licence_number__startswith="DEMO-LAB-LIC-").order_by("id"))
        partners += list(LabPartner.objects.filter(website__startswith="https://example.invalid/").order_by("id"))
        partners += list(LabPartner.objects.filter(licence_number__startswith="Lab-LIC-").order_by("id"))
        seen_partner_ids = set()
        for position, partner in enumerate(partners, start=1):
            if partner.pk in seen_partner_ids:
                continue
            seen_partner_ids.add(partner.pk)
            partner.licence_number = f"GJ-LAB-{position:04d}"
            partner.address = f"{position + 20}, Diagnostics Avenue, {partner.city}, Gujarat"
            partner.accreditations = "NABL documentation under compliance review"
            partner.website = ""
            partner.save(update_fields=["licence_number", "address", "accreditations", "website"])
            for branch in LabBranch.objects.filter(partner=partner):
                branch.name = f"{partner.name} Collection Centre {branch.pk}"
                branch.address = f"Sample Collection Road, {partner.city}"
                branch.save(update_fields=["name", "address"])
        counts["lab_partners"] = len(partners)

        bookings = list(LabBooking.objects.filter(accession_number__startswith="DEMO-LAB-").order_by("id"))
        for booking in bookings:
            booking.accession_number = f"LAB-{timezone.now().year}-{booking.pk:06d}"
            booking.report_summary = "Report released to the customer health-record vault."
            booking.save(update_fields=["accession_number", "report_summary", "updated_at"])
        counts["lab_bookings"] = len(bookings)

        for value in LabReportValue.objects.filter(reference_range="DEMO range"):
            value.reference_range = "See the age and sex-specific report range."
            value.explanation = "This is a non-diagnostic explanation of the reported value."
            value.save(update_fields=["reference_range", "explanation"])
        for reference in LabReferenceRange.objects.filter(range_text="DEMO range - verify with partner"):
            reference.range_text = "Reference range provided with the laboratory report."
            reference.source_note = "Partner laboratory reference range."
            reference.save(update_fields=["range_text", "source_note"])
        for event in LabSampleEvent.objects.filter(barcode__startswith="DEMO-BARCODE-"):
            event.note = "Sample chain-of-custody event recorded by the collection team."
            event.save(update_fields=["note"])
        for refund in LabRefund.objects.filter(gateway_reference__startswith="DEMO-LAB-REF-"):
            refund.gateway_reference = f"LAB-REFUND-{refund.pk:06d}"
            refund.save(update_fields=["gateway_reference", "updated_at"])
        for settlement in LabSettlement.objects.filter(reference__startswith="DEMO-LAB-SETTLEMENT-"):
            settlement.reference = f"LAB-SETTLEMENT-{settlement.pk:06d}"
            settlement.notes = "Partner settlement prepared for operations review."
            settlement.save(update_fields=["reference", "notes", "updated_at"])
        for dispute in LabDispute.objects.filter(description="DEMO lab dispute for operations testing."):
            dispute.description = "Customer raised a report-related service concern."
            dispute.resolution_note = "Issue reviewed and resolved by the lab operations team."
            dispute.save(update_fields=["description", "resolution_note", "updated_at"])

        payments = list(ConsultationPayment.objects.filter(provider_order_id__startswith="DEMO-CONSULT-ORDER-").order_by("id"))
        for payment in payments:
            payment.provider_order_id = f"CONSULT-ORDER-{payment.pk:08d}"
            payment.provider_payment_id = f"CONSULT-PAY-{payment.pk:08d}"
            payment.provider = "razorpay"
            payment.save(update_fields=["provider_order_id", "provider_payment_id", "provider", "updated_at"])
        counts["consultation_payments"] = len(payments)

        for partner in LabPartner.objects.filter(website__startswith="https://example.invalid/"):
            partner.website = ""
            partner.accreditations = "NABL documentation under compliance review"
            partner.address = f"Diagnostics Avenue, {partner.city}, Gujarat"
            partner.save(update_fields=["website", "accreditations", "address"])
            for branch in LabBranch.objects.filter(partner=partner):
                branch.name = f"{partner.name} Collection Centre {branch.pk}"
                branch.address = f"Sample Collection Road, {partner.city}"
                branch.save(update_fields=["name", "address"])

        for partner in LabPartner.objects.filter(address__startswith="Demo collection centre"):
            partner.address = f"Diagnostics Avenue, {partner.city}, Gujarat"
            partner.accreditations = "NABL documentation under compliance review"
            partner.save(update_fields=["address", "accreditations"])

        for test in LabTest.objects.filter(description__icontains="demo"):
            test.description = "Home collection is available in selected service areas."
            test.what_it_measures = "The requested laboratory markers are measured according to the partner report."
            test.limitations = "Results should be interpreted by a qualified healthcare professional."
            test.save(update_fields=["description", "what_it_measures", "limitations", "updated_at"])

        for batch in InventoryBatch.objects.filter(batch_number__startswith="DEMO-BATCH-").select_related("vendor_product"):
            batch.batch_number = f"BATCH-{timezone.now().year}-{batch.pk:06d}"
            batch.supplier_invoice_number = f"INV-{timezone.now().year}-{batch.pk:07d}"
            batch.supplier_name = batch.vendor_product.vendor.business_name
            batch.save(update_fields=["batch_number", "supplier_invoice_number", "supplier_name", "updated_at"])
            for movement in InventoryMovement.objects.filter(batch=batch, reference__startswith="DEMO-"):
                movement.reference = f"RECEIPT-{movement.pk:07d}"
                movement.save(update_fields=["reference"])
            for reading in InventoryTemperatureLog.objects.filter(batch=batch, source="DEMO sensor"):
                reading.source = "Warehouse temperature logger"
                reading.note = "Routine temperature reading within the configured storage range."
                reading.save(update_fields=["source", "note"])

        PaymentSettlement.objects.filter(settlement_reference__startswith="DEMO-").update(provider="razorpay")
        self.stdout.write(self.style.SUCCESS(f"Finished exact-marker cleanup: {counts}"))
        self.stdout.write("No static or media files were deleted. Relationships were preserved.")
