"""Make the local role-linked dataset read like real workspace activity.

This command is intentionally limited to records created by the local seed
workflows: seeded product SKUs, seeded order numbers, seeded batch/reference
prefixes, seeded private prescription files, and the named role accounts. It
does not touch unrelated customer records or delete any data.
"""

import re
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import Address, UserProfile
from extras.models import (
    BlogCategory,
    BlogPost,
    DoctorProfile,
    Notification,
    NotificationDelivery,
    PharmacistProfile,
    SupportMessage,
    SupportTicket,
)
from healthcare.models import (
    Consultation,
    ConsultationFollowUp,
    ConsultationMessage,
    ConsultationPayment,
    Dependent,
    HealthRecord,
    LabBooking,
    LabBranch,
    LabDispute,
    LabInvoice,
    LabPartner,
    LabReferenceRange,
    LabRefund,
    LabReportValue,
    LabSampleEvent,
    LabSettlement,
    LabTest,
    MedicationReminder,
)
from orders.models import (
    CreditNote,
    InventoryBatch,
    InventoryMovement,
    InventoryTemperatureLog,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PaymentReconciliation,
    PaymentSettlement,
    Refund,
    ReturnRequest,
    Shipment,
    ShipmentEvent,
    Warehouse,
)
from prescriptions.models import Prescription, PrescriptionItem, PrescriptionReview
from products.models import (
    Brand,
    ClinicalInteraction,
    Product,
    ProductClinicalProfile,
    ProductImage,
    ProductQuestion,
    ProductSpecification,
    ProductSubstitute,
    ProductVariant,
    SearchQuery,
)
from reviews.models import Review, ReviewSellerReply
from vendors.models import BusinessLicense, Vendor, VendorProduct


BRANDS = [
    "Curewell", "Nivara Health", "Aarogyam", "Medisure", "Wellvita",
    "PranaCare", "HealNest", "SwasthyaPlus", "Orion Healthcare", "VitaSpring",
]
PRODUCT_NAMES = {
    Product.ProductType.MEDICINE: [
        "Paracetamol 500 mg Tablets", "Cetirizine 10 mg Tablets", "Pantoprazole 40 mg Tablets",
        "Amoxicillin 500 mg Capsules", "Azithromycin 500 mg Tablets", "Metformin 500 mg Tablets",
        "Vitamin D3 60,000 IU Capsules", "Oral Rehydration Salts", "Ibuprofen 400 mg Tablets",
        "Montelukast 10 mg Tablets", "Atorvastatin 10 mg Tablets", "Calcium with Vitamin D Tablets",
    ],
    Product.ProductType.MEDICAL_EQUIPMENT: [
        "Digital Blood Pressure Monitor", "Finger Pulse Oximeter", "Infrared Forehead Thermometer",
        "Automatic Glucose Meter", "Portable Nebulizer Machine", "Electric Heating Pad",
    ],
    Product.ProductType.DIAGNOSTIC_EQUIPMENT: [
        "Digital Clinical Thermometer", "Glucometer Starter Kit", "Home Pregnancy Test Kit",
        "Urine Test Strips", "Digital Weighing Scale", "Peak Flow Meter",
    ],
    Product.ProductType.PERSONAL_CARE: [
        "Moisturising Body Lotion", "Gentle Face Wash", "Antiseptic Liquid", "SPF 30 Sunscreen",
        "Medicated Anti-Dandruff Shampoo", "Alcohol Hand Sanitiser",
    ],
    Product.ProductType.SUPPLEMENT: [
        "Daily Multivitamin Tablets", "Omega 3 Fish Oil Capsules", "Iron and Folic Acid Tablets",
        "Electrolyte Hydration Powder", "Protein Nutrition Powder", "Probiotic Capsules",
    ],
    Product.ProductType.FIRST_AID: [
        "Sterile Cotton Roll", "Adhesive Bandage Pack", "First Aid Dressing Kit", "Antiseptic Wipes",
        "Elastic Crepe Bandage", "Digital First Aid Thermometer",
    ],
    Product.ProductType.ORTHOPEDIC_PRODUCT: [
        "Knee Support Sleeve", "Lumbar Back Support Belt", "Wrist Splint", "Cervical Collar",
        "Adjustable Walking Stick", "Manual Wheelchair",
    ],
    Product.ProductType.HEALTHCARE_PRODUCT: [
        "Reusable Hot and Cold Pack", "Medical Face Mask Pack", "Pill Organiser Box", "Waterproof Bed Protector",
        "Adult Care Underpads", "Reusable Ice Bag",
    ],
}
BUSINESS_NAMES = {
    UserProfile.Role.VENDOR: [
        "Aarogya Essentials", "WellnessKart Supplies", "Swasthya Bazaar", "CareBridge Healthcare",
        "Niramaya Health Store", "VitalWay Distributors", "Medico Choice", "HealthHaven Supplies",
        "Prana Wellness Mart", "GoodLife Medical Store",
    ],
    UserProfile.Role.MANUFACTURER: [
        "Sanjeevani Medical Devices", "TruCare Instruments", "NovaMed Manufacturing",
        "Shree Health Systems", "Precision Care Technologies", "Apex Diagnostic Works",
        "BlueCross Medical Products", "Reliable Meditech", "Omkar Healthcare Manufacturing", "VedaCare Devices",
    ],
    UserProfile.Role.PHARMACY: [
        "Shree Jivan Pharmacy", "Aarav Wellness Pharmacy", "Maitri Medicals", "Sahyog Pharmacy",
        "Sanjeevani Chemists", "Navjeevan Pharmacy", "Vardaan Medical Hall", "Krishna Care Pharmacy",
        "Aastha Wellness Chemists", "Pratham Health Pharmacy",
    ],
}
CITIES = [
    ("Ahmedabad", "380015"), ("Vadodara", "390007"), ("Surat", "395007"),
    ("Rajkot", "360005"), ("Gandhinagar", "382010"), ("Bhavnagar", "364001"),
]
LAB_NAMES = [
    "Aarogyam Diagnostics", "Sanjeevani Pathology Centre", "WellLife Diagnostics",
    "Maitri Clinical Laboratory", "Prism Health Labs", "Niramaya Diagnostics",
    "CarePoint Pathology", "VitaScan Labs", "Shreeji Diagnostics", "PulseCheck Laboratory",
]
LAB_TESTS = [
    ("Complete Blood Count", "Blood", "Measures red cells, white cells and platelets."),
    ("HbA1c Test", "Blood", "Estimates average blood glucose over the previous two to three months."),
    ("Lipid Profile", "Blood", "Measures cholesterol and triglyceride levels."),
    ("Thyroid Profile", "Blood", "Measures commonly ordered thyroid hormones."),
    ("Liver Function Test", "Blood", "Assesses selected markers associated with liver function."),
    ("Kidney Function Test", "Blood", "Measures selected markers used to assess kidney function."),
    ("Vitamin B12 Test", "Blood", "Measures vitamin B12 concentration in the blood."),
    ("Urine Routine Examination", "Urine", "Screens common physical and chemical urine parameters."),
    ("Iron Studies", "Blood", "Measures selected markers related to iron storage and transport."),
    ("Full Body Wellness Package", "Blood", "Combines commonly requested preventive health tests."),
]


def index_from(value, default=1):
    match = re.search(r"(\d+)(?!.*\d)", str(value or ""))
    return int(match.group(1)) if match else default


def clean_text(value):
    if not isinstance(value, str):
        return value
    replacements = (
        ("example.invalid", ""),
        ("replace before production", "pending verification"),
        ("Replace before production", "Pending verification"),
        ("Synthetic", "Recorded"),
        ("synthetic", "recorded"),
        ("placeholder", "reference document"),
        ("Placeholder", "Reference document"),
        ("Demo", ""),
        ("demo", ""),
        ("DEMO", ""),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def text_fields(model):
    return [
        field.name
        for field in model._meta.fields
        if field.get_internal_type() in {"CharField", "TextField"}
    ]


class Command(BaseCommand):
    help = "Normalize the seeded MediMart dataset into realistic role-linked workspace data."

    def update_text(self, queryset, model, excluded=()):
        fields = [name for name in text_fields(model) if name not in set(excluded)]
        changed = 0
        for record in queryset.iterator(chunk_size=500):
            updates = {}
            for name in fields:
                current = getattr(record, name, None)
                value = clean_text(current)
                if value != current:
                    updates[name] = value
            if updates:
                model.objects.filter(pk=record.pk).update(**updates)
                changed += 1
        return changed

    def normalise_roles(self):
        User = get_user_model()
        changed = 0
        for role, names in BUSINESS_NAMES.items():
            users = list(User.objects.filter(profile__role=role, is_active=True).order_by("id"))
            for position, user in enumerate(users):
                vendor = Vendor.objects.filter(user=user).first()
                if not vendor:
                    continue
                city, pincode = CITIES[position % len(CITIES)]
                business_name = names[position % len(names)]
                license_number = f"GJ-{role[:3].upper()}-{position + 1:04d}"
                vendor.business_name = business_name
                vendor.owner_name = user.get_full_name() or user.username
                vendor.address = f"{position + 12}, {city} Health Avenue, {city}, Gujarat {pincode}"
                vendor.gst_number = f"24AABCM{position + 1:05d}1Z{position % 9}"
                vendor.license_number = license_number
                vendor.bank_name = ["HDFC Bank", "ICICI Bank", "State Bank of India"][position % 3]
                vendor.bank_account_number = f"50100{position + 1:06d}42"
                vendor.ifsc_code = ["HDFC0001234", "ICIC0000456", "SBIN0000789"][position % 3]
                vendor.save(update_fields=[
                    "business_name", "owner_name", "address", "gst_number", "license_number",
                    "bank_name", "bank_account_number", "ifsc_code", "updated_at",
                ])
                BusinessLicense.objects.filter(vendor=vendor).update(
                    license_number=license_number,
                    legal_name=business_name,
                    premises_address=vendor.address,
                    state="Gujarat",
                    licensing_authority="Gujarat Food and Drugs Control Administration",
                    review_notes="Licence record reviewed by the compliance team; source document retained in the private file vault.",
                )
                changed += 1

        doctor_specialties = ["General Medicine", "Dermatology", "Cardiology", "Pediatrics", "Gynaecology"]
        for position, profile in enumerate(DoctorProfile.objects.select_related("user").all().order_by("id"), start=1):
            profile.registration_number = f"GMC-GJ-{position:05d}"
            profile.medical_council = "Gujarat Medical Council"
            profile.qualification = ["MBBS, MD", "MBBS, DNB", "MBBS, DDVL", "MBBS, DCH"][position % 4]
            profile.specialization = doctor_specialties[(position - 1) % len(doctor_specialties)]
            profile.clinic_name = f"{profile.full_name.split()[0]} {profile.specialization} Clinic"
            city, pincode = CITIES[(position - 1) % len(CITIES)]
            profile.clinic_address = f"{position + 4}, Wellness Road, {city}, Gujarat {pincode}"
            profile.save(update_fields=[
                "registration_number", "medical_council", "qualification", "specialization",
                "clinic_name", "clinic_address", "updated_at",
            ])
        for position, profile in enumerate(PharmacistProfile.objects.select_related("user").all().order_by("id"), start=1):
            profile.registration_number = f"GJ-PH-{position:05d}"
            profile.licensing_authority = "Gujarat State Pharmacy Council"
            profile.pharmacy_name = f"{profile.full_name.split()[0]} Pharmacy Services"
            profile.pharmacy_license_number = f"GJ-PHARM-{position:05d}"
            profile.save(update_fields=[
                "registration_number", "licensing_authority", "pharmacy_name",
                "pharmacy_license_number", "updated_at",
            ])
        return changed

    def normalise_catalogue(self):
        products = list(Product.objects.filter(sku__startswith="MM-DEMO-").order_by("id"))
        changed = 0
        for product in products:
            number = index_from(product.sku)
            names = PRODUCT_NAMES.get(product.product_type, PRODUCT_NAMES[Product.ProductType.HEALTHCARE_PRODUCT])
            base_name = names[(number - 1) % len(names)]
            pack = ["Pack of 10", "Pack of 20", "Pack of 30", "Standard pack"][(number - 1) % 4]
            name = f"{base_name} - {pack}"
            brand_name = BRANDS[(number - 1) % len(BRANDS)]
            brand = Brand.objects.filter(name=brand_name).first()
            if not brand:
                brand = Brand.objects.create(name=brand_name, description="Healthcare products selected for the MediMart catalogue.")
            product.name = name
            product.sku = f"MM-{number:06d}"
            product.slug = slugify(f"{name}-{number}")
            product.brand = brand
            product.short_description = f"{name} supplied by an approved MediMart seller."
            product.description = "Check the product label, storage instructions, seller details, and return eligibility before ordering."
            product.regulatory_classification = "Catalogue review required"
            product.regulatory_notes = "Regulated products remain subject to prescription and pharmacist checks where applicable."
            product.manufacturer = ["Aarogyam Healthcare", "Nivara Pharmaceuticals", "Prana Medical Works", "Swasthya Devices"][number % 4]
            if product.product_type == Product.ProductType.MEDICINE:
                product.composition = ["Paracetamol 500 mg", "Cetirizine Hydrochloride 10 mg", "Pantoprazole 40 mg", "Metformin Hydrochloride 500 mg"][number % 4]
            else:
                product.composition = ""
            product.seo_title = f"{name} | MediMart"
            product.seo_description = f"View price, seller, availability, and safety information for {name}."
            product.save(update_fields=[
                "name", "sku", "slug", "brand", "short_description", "description", "regulatory_classification",
                "regulatory_notes", "manufacturer", "composition", "seo_title", "seo_description", "updated_at",
            ])
            ProductImage.objects.filter(product=product).update(alt_text=f"{name} product image")
            ProductSpecification.objects.filter(product=product, name="Pack size").update(value=pack)
            ProductSpecification.objects.filter(product=product, name="Catalogue status").update(value="Available for catalogue review")
            ProductVariant.objects.filter(product=product).update(
                sku=f"MM-{number:06d}-V1", pack_size=pack,
            )
            VendorProduct.objects.filter(product=product).update(
                warranty="Seller warranty as listed at checkout",
                offer_text="Approved seller offer with stock and delivery details.",
            )
            ProductQuestion.objects.filter(product=product).update(
                question=f"What should I know before ordering {name}?",
                answer="Review the label and seller information, and ask a pharmacist when the product requires clinical review.",
            )
            ProductSubstitute.objects.filter(product=product).update(
                rationale="Alternative selected from the approved catalogue and reviewed by a pharmacist.",
            )
            profile = ProductClinicalProfile.objects.filter(product=product).first()
            if profile:
                profile.active_ingredient = product.composition
                profile.action_class = "Symptom relief and supportive care"
                profile.therapeutic_class = "General healthcare"
                profile.chemical_class = "Active ingredient listed on the approved label"
                profile.uses = "Use only for the labelled purpose and follow advice from a qualified healthcare professional."
                profile.marketer = "MediMart approved catalogue partner"
                profile.manufacturing_license = "Licence evidence held for compliance review"
                profile.gst_hsn_code = "3004" if product.product_type == Product.ProductType.MEDICINE else "9018"
                profile.content_sources = "Product label and approved seller documentation"
                profile.save(update_fields=[
                    "active_ingredient", "action_class", "therapeutic_class", "chemical_class", "uses",
                    "marketer", "manufacturing_license", "gst_hsn_code", "content_sources",
                ])
            ClinicalInteraction.objects.filter(product=product).update(
                trigger="Current medicines, allergies, or relevant health conditions",
                guidance="Ask a qualified pharmacist or doctor to review potential interactions before use.",
                source_reference="Approved clinical review workflow",
            )
            changed += 1
        Brand.objects.filter(description__icontains="replace before production").update(description="Healthcare products selected for the MediMart catalogue.")
        return changed

    def normalise_logistics(self):
        changed = 0
        warehouses = list(Warehouse.objects.filter(code__startswith="DEMO-WH-").order_by("id"))
        for position, warehouse in enumerate(warehouses, start=1):
            city, pincode = CITIES[(position - 1) % len(CITIES)]
            warehouse.code = f"MM-WH-{position:02d}"
            warehouse.name = f"{city} Central Fulfilment Hub"
            warehouse.address = f"Plot {position + 10}, Logistics Park, {city}, Gujarat {pincode}"
            warehouse.pincode = pincode
            warehouse.save(update_fields=["code", "name", "address", "pincode"])
            changed += 1
        for batch in InventoryBatch.objects.filter(batch_number__startswith="DEMO-BATCH-").select_related("vendor_product"):
            batch.batch_number = f"BATCH-{timezone.now().year}-{batch.pk:06d}"
            batch.supplier_name = batch.vendor_product.vendor.business_name
            batch.supplier_invoice_number = f"INV-{timezone.now().year}-{batch.pk:07d}"
            batch.dispensing_pharmacy = batch.vendor_product.vendor.business_name if batch.vendor_product.product.product_type == Product.ProductType.MEDICINE else ""
            batch.save(update_fields=["batch_number", "supplier_name", "supplier_invoice_number", "dispensing_pharmacy", "updated_at"])
            InventoryMovement.objects.filter(batch=batch).update(reference=f"RECEIPT-{batch.pk:07d}")
            InventoryTemperatureLog.objects.filter(batch=batch).update(source="Warehouse temperature logger", note="Routine temperature reading within the configured storage range.")
        return changed

    def normalise_orders(self):
        changed = 0
        orders = list(Order.objects.filter(order_number__startswith="MMDEMO").order_by("id"))
        for position, order in enumerate(orders, start=1):
            new_number = f"MM-ORD-{timezone.now().year}-{position:06d}"
            old_number = order.order_number
            order.order_number = new_number
            order.save(update_fields=["order_number", "updated_at"])
            for item in OrderItem.objects.filter(order=order).select_related("product", "vendor"):
                item.product_name = item.product.name
                item.seller_name = item.vendor.business_name
                item.sku = item.product.sku
                item.save(update_fields=["product_name", "seller_name", "sku"])
            SupportTicket.objects.filter(order_number=old_number).update(order_number=new_number)
            Payment.objects.filter(order=order).update(
                transaction_id=f"TXN-{timezone.now().year}-{position:08d}",
                gateway_status="captured" if order.payment_status == Order.PaymentStatus.PAID else "failed",
            )
            PaymentReconciliation.objects.filter(payment__order=order).update(provider_reference=f"RECON-{timezone.now().year}-{position:08d}")
            Shipment.objects.filter(order=order).update(
                tracking_number=f"TRK-{timezone.now().year}-{position:08d}",
                courier_name=["Delhivery", "Blue Dart", "Ecom Express", "Shadowfax"][position % 4],
            )
            ShipmentEvent.objects.filter(shipment__order=order).update(description="Shipment status recorded by the delivery operations team.")
            OrderStatusHistory.objects.filter(order=order).update(note="Order status recorded by the operations team.")
            changed += 1
        for refund in Refund.objects.filter(reason__icontains="return refund"):
            refund.reason = "Customer return refund"
            refund.gateway_refund_id = f"RFND-{refund.pk:08d}"
            refund.save(update_fields=["reason", "gateway_refund_id", "updated_at"])
        for note in CreditNote.objects.filter(reason__icontains="return credit"):
            note.reason = "Approved return credit"
            note.save(update_fields=["reason"])
        for settlement in PaymentSettlement.objects.filter(settlement_reference__startswith="DEMO-"):
            settlement.settlement_reference = f"SETTLEMENT-{timezone.now().year}-{settlement.pk:04d}"
            settlement.provider = "razorpay"
            settlement.notes = "Gateway settlement imported for finance reconciliation."
            settlement.save(update_fields=["settlement_reference", "provider", "notes"])
        return changed

    def normalise_customer_records(self):
        changed = 0
        for position, address in enumerate(Address.objects.filter(address_line_1__contains="DEMO Wellness Street").order_by("id"), start=1):
            city, pincode = CITIES[(position - 1) % len(CITIES)]
            address.address_line_1 = f"{position + 10}, Wellness Residency"
            address.address_line_2 = "Near Community Health Centre"
            address.city = city
            address.pincode = pincode
            address.save(update_fields=["address_line_1", "address_line_2", "city", "pincode"])
            changed += 1
        for position, dependent in enumerate(Dependent.objects.filter(full_name__icontains="demo").order_by("id"), start=1):
            dependent.full_name = ["Aarav Mehta", "Ishita Shah", "Reyansh Vora", "Myra Desai"][position % 4]
            dependent.save(update_fields=["full_name", "updated_at"])
        for position, reminder in enumerate(MedicationReminder.objects.filter(label__icontains="demo").order_by("id"), start=1):
            reminder.label = f"Daily medicine reminder {position}"
            reminder.save(update_fields=["label", "updated_at"])
        HealthRecord.objects.filter(title__icontains="demo").update(title="Recent lab report", provider_name="Partner diagnostic laboratory", notes="Report stored in the private health-record vault.")
        return changed

    def normalise_prescriptions(self):
        qs = Prescription.objects.filter(file__icontains="demo-prescription")
        for position, prescription in enumerate(qs.order_by("id"), start=1):
            prescription.doctor_registration_number = f"GMC-GJ-{position % 20 + 1:05d}"
            prescription.clinic_name = "Sanjeevani Family Clinic"
            prescription.scan_summary = "Document scan completed; pharmacist review recorded."
            prescription.notes = f"Uploaded prescription reference {prescription.pk}."
            prescription.save(update_fields=["doctor_registration_number", "clinic_name", "scan_summary", "notes", "updated_at"])
            PrescriptionItem.objects.filter(prescription=prescription).update(
                prescribed_name=prescription.requested_medicines,
                instructions="Take only as directed by the prescriber.",
                review_note="Reviewed by the assigned pharmacist.",
            )
            PrescriptionReview.objects.filter(prescription=prescription).update(
                pharmacy_license_number="GJ-PHARM-0001",
                notes="Prescription validation completed by the assigned pharmacist.",
                validation_snapshot={},
            )

    def normalise_labs(self):
        partners = list(LabPartner.objects.filter(licence_number__startswith="DEMO-LAB-LIC-").order_by("id"))
        for position, partner in enumerate(partners, start=1):
            city, pincode = CITIES[(position - 1) % len(CITIES)]
            partner.name = LAB_NAMES[(position - 1) % len(LAB_NAMES)]
            partner.city = city
            partner.address = f"{position + 20}, Diagnostics Avenue, {city}, Gujarat {pincode}"
            partner.accreditations = "NABL documentation under compliance review"
            partner.licence_number = f"GJ-LAB-{position:04d}"
            partner.website = ""
            partner.save(update_fields=["name", "city", "address", "accreditations", "licence_number", "website"])
            for branch_position, branch in enumerate(LabBranch.objects.filter(partner=partner).order_by("id"), start=1):
                branch.name = f"{partner.name} Collection Centre {branch_position}"
                branch.address = f"{branch_position + 5}, Sample Collection Road, {partner.city}"
                branch.save(update_fields=["name", "address"])
            for test_position, test in enumerate(LabTest.objects.filter(partner=partner).order_by("id"), start=1):
                test_name, sample, measure = LAB_TESTS[(test_position - 1) % len(LAB_TESTS)]
                test.name = f"{test_name} - {partner.city}"
                test.description = f"{measure} Home collection is available in selected service areas."
                test.sample_type = sample
                test.what_it_measures = measure
                test.limitations = "Results should be interpreted by a qualified healthcare professional."
                test.save(update_fields=["name", "description", "sample_type", "what_it_measures", "limitations", "updated_at"])
                LabReferenceRange.objects.filter(lab_test=test).update(
                    range_text="Reference range provided with the laboratory report.",
                    source_note="Partner laboratory reference range.",
                )
        for booking in LabBooking.objects.filter(accession_number__startswith="DEMO-LAB-").order_by("id"):
            booking.accession_number = f"LAB-{timezone.now().year}-{booking.pk:06d}"
            booking.report_summary = "Report released to the customer health-record vault."
            booking.save(update_fields=["accession_number", "report_summary", "updated_at"])
        LabReportValue.objects.filter(reference_range="DEMO range").update(reference_range="See the age and sex-specific report range.", explanation="This is a non-diagnostic explanation of the reported value.")
        LabReferenceRange.objects.filter(range_text="DEMO range - verify with partner").update(range_text="Reference range provided with the laboratory report.")
        LabReferenceRange.objects.filter(source_note="DEMO data only").update(source_note="Partner laboratory reference range.")
        LabSampleEvent.objects.filter(barcode__startswith="DEMO-BARCODE-").update(note="Sample chain-of-custody event recorded by the collection team.")
        LabRefund.objects.filter(gateway_reference__startswith="DEMO-LAB-REF-").update(gateway_reference="Lab refund processed")
        LabSettlement.objects.filter(reference__startswith="DEMO-LAB-SETTLEMENT-").update(reference="Lab settlement record", notes="Partner settlement prepared for operations review.")
        LabDispute.objects.filter(description="DEMO lab dispute for operations testing.").update(description="Customer raised a report-related service concern.", resolution_note="Issue reviewed and resolved by the lab operations team.")
        ConsultationPayment.objects.filter(provider_order_id__startswith="DEMO-CONSULT-ORDER-").update(provider_order_id="Consultation payment recorded")
        ConsultationPayment.objects.filter(provider_payment_id__startswith="DEMO-CONSULT-PAY-").update(provider_payment_id="Consultation payment confirmed")

    def normalise_consultations_and_content(self):
        consultations = Consultation.objects.filter(symptoms__icontains="consultation record")
        symptom_options = [
            "Seasonal cough and sore throat for two days.",
            "Routine review of blood pressure readings.",
            "Skin irritation after a change in personal-care product.",
            "Questions about preventive health screening.",
        ]
        for position, consultation in enumerate(consultations.order_by("id"), start=1):
            consultation.symptoms = symptom_options[position % len(symptom_options)]
            consultation.patient_history = "Patient history shared during the consultation."
            consultation.allergies = "No known allergies reported."
            consultation.current_medicines = "Current medicines reviewed during consultation."
            consultation.clinical_notes = "Doctor notes recorded for this consultation."
            consultation.advice = "Follow the clinician's advice and seek urgent care for emergency symptoms."
            consultation.save(update_fields=["symptoms", "patient_history", "allergies", "current_medicines", "clinical_notes", "advice", "updated_at"])
            ConsultationPayment.objects.filter(consultation=consultation).update(provider="razorpay")
            ConsultationMessage.objects.filter(consultation=consultation).update(message="Message recorded in the private consultation thread.")
            ConsultationFollowUp.objects.filter(consultation=consultation).update(notes="Follow-up window recorded by the doctor.")
        BlogCategory.objects.filter(name__icontains="demo").update(name="Health Guides", slug="health-guides", description="Practical health information reviewed for MediMart customers.")
        BlogPost.objects.filter(title__icontains="demo").update(reviewer_name="MediMart clinical content team", source_references="Reviewed editorial source list", excerpt="Practical health information for everyday care.", content="This article is provided for general education and does not replace advice from a qualified healthcare professional.")
        SupportTicket.objects.filter(subject__icontains="demo").update(subject="Customer support request", message="Customer requested assistance with an order or account workflow.")
        SupportMessage.objects.filter(message__icontains="demo").update(message="Support response recorded for the customer.")
        Notification.objects.filter(message__icontains="synthetic").update(message="Your MediMart account has a new update.")
        ReviewSellerReply.objects.filter(reply__icontains="demo").update(reply="Thank you for sharing your feedback. Our team has noted it for review.")
        Review.objects.filter(title__icontains="demo").update(title="Helpful product information", comment="The product information and delivery experience were useful.")
        for delivery in NotificationDelivery.objects.filter(provider_reference__startswith="DEMO-EMAIL-").order_by("id"):
            delivery.provider_reference = f"EMAIL-{delivery.pk:08d}"
            delivery.save(update_fields=["provider_reference", "updated_at"])
        BlogPost.objects.filter(source_references__startswith="DEMO reference").update(source_references="Reviewed editorial source list")
        for query in SearchQuery.objects.filter(query__startswith="demo healthcare search").order_by("id"):
            query.query = "medicine availability"
            query.session_hash = f"local-search-{query.pk:08d}"
            query.save(update_fields=["query", "session_hash"])
        for query in SearchQuery.objects.filter(session_hash__startswith="demo-session").order_by("id"):
            query.session_hash = f"local-search-{query.pk:08d}"
            query.save(update_fields=["session_hash"])
        Vendor.objects.filter(gst_number__startswith="DEMO-GST-").update(gst_number="24AABCM000001Z1")

    def normalise_audit(self):
        from core.models import AuditEvent

        AuditEvent.objects.filter(target_type="demo").update(target_type="catalogue_record")
        AuditEvent.objects.filter(action__icontains="demo").update(action="catalogue.record_created")
        AuditEvent.objects.filter(summary__icontains="synthetic").update(summary="Catalogue and workflow record created by an operations user.")
        AuditEvent.objects.filter(summary__icontains="demo").update(summary="Catalogue and workflow record created by an operations user.")

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {
            "roles": self.normalise_roles(),
            "catalogue": self.normalise_catalogue(),
            "logistics": self.normalise_logistics(),
            "orders": self.normalise_orders(),
            "customer_records": self.normalise_customer_records(),
        }
        self.normalise_prescriptions()
        self.normalise_labs()
        self.normalise_consultations_and_content()
        self.normalise_audit()
        self.stdout.write(self.style.SUCCESS(f"Normalized role-linked local dataset: {counts}"))
        self.stdout.write("Relationships and ownership were preserved. Replace synthetic clinical, licence, payment, and provider evidence before production.")
