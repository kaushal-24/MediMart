"""Create a large, clearly-marked local dataset across MediMart workflows.

This command is intentionally for local development and QA. It creates synthetic
records with DEMO markers; it does not represent real licences, clinical advice,
payment captures, or provider events.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Address, UserProfile
from cart.models import Cart, CartItem, Wishlist, WishlistItem
from core.models import AuditEvent
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
    DoctorAvailability,
    HealthRecord,
    LabBooking,
    LabBranch,
    LabCollectionSlot,
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
    Coupon,
    CouponUsage,
    CreditNote,
    InventoryBatch,
    InventoryMovement,
    InventoryTemperatureLog,
    Order,
    OrderChargeBreakdown,
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
    Category,
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
from reviews.models import Review, ReviewAbuseReport, ReviewHelpfulVote, ReviewSellerReply
from vendors.models import BusinessLicense, Vendor, VendorProduct


DEMO = "DEMO"
DEFAULT_PRODUCT_COUNT = 1000
DEFAULT_ORDER_COUNT = 1200
DEFAULT_REVIEW_COUNT = 3000
IMAGE_NAMES = ("medicine.jpg", "pills.jpg", "bottle.jpg", "ibuprofen.jpg")


class Command(BaseCommand):
    help = "Create a large repeatable synthetic MediMart dataset for local QA."

    def add_arguments(self, parser):
        parser.add_argument("--products", type=int, default=DEFAULT_PRODUCT_COUNT)
        parser.add_argument("--orders", type=int, default=DEFAULT_ORDER_COUNT)
        parser.add_argument("--reviews", type=int, default=DEFAULT_REVIEW_COUNT)
        parser.add_argument("--notifications", type=int, default=2500)

    def image_path(self, index):
        return f"demo-seed/{IMAGE_NAMES[index % len(IMAGE_NAMES)]}"

    def demo_file(self, relative_name, content):
        target = Path(settings.PRIVATE_MEDIA_ROOT) / "demo-seed" / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(content)
        return f"demo-seed/{relative_name}"

    @staticmethod
    def first_or_none(items):
        return items[0] if items else None

    @staticmethod
    def get_users(role):
        User = get_user_model()
        return list(User.objects.filter(profile__role=role, is_active=True).order_by("id"))

    @staticmethod
    def bulk(model, objects):
        if objects:
            model.objects.bulk_create(objects, batch_size=500, ignore_conflicts=True)

    @staticmethod
    def marker_exists(model, field, marker):
        return model.objects.filter(**{f"{field}__startswith": marker}).exists()

    def seed_catalogue(self, count, admin, pharmacists):
        parent_names = [
            "Medicines", "Medical Equipment", "Surgical Equipment", "Diagnostic Equipment",
            "Personal Care", "Supplements", "Baby Care", "Orthopedic Products",
        ]
        parents = {}
        for name in parent_names:
            parents[name], _ = Category.objects.get_or_create(name=name)

        child_names = [
            "Pain Relief", "Cold and Cough", "Diabetes Care", "Heart Care", "Digestive Health",
            "Vitamins", "Skin Care", "First Aid", "Mobility Aids", "Respiratory Care",
            "Home Diagnostics", "Wound Care", "Dental Care", "Baby Wellness", "Fitness Recovery",
        ]
        categories = []
        for index, name in enumerate(child_names):
            parent = parents[parent_names[index % len(parent_names)]]
            category = Category.objects.filter(name=name).first()
            if category is None:
                category = Category.objects.create(name=name, parent=parent)
            categories.append(category)

        brands = []
        for index in range(1, 31):
            brand, _ = Brand.objects.get_or_create(
                name=f"MediMart Demo Brand {index:02d}",
                defaults={
                    "description": "Synthetic local-development brand data. Replace before production.",
                    "logo": self.image_path(index),
                },
            )
            brands.append(brand)

        product_types = [
            Product.ProductType.MEDICINE,
            Product.ProductType.MEDICAL_EQUIPMENT,
            Product.ProductType.DIAGNOSTIC_EQUIPMENT,
            Product.ProductType.PERSONAL_CARE,
            Product.ProductType.SUPPLEMENT,
            Product.ProductType.FIRST_AID,
            Product.ProductType.ORTHOPEDIC_PRODUCT,
            Product.ProductType.HEALTHCARE_PRODUCT,
        ]
        medicines = []
        products = []
        for index in range(1, count + 1):
            product_type = product_types[(index - 1) % len(product_types)]
            is_medicine = product_type == Product.ProductType.MEDICINE
            is_rx = is_medicine and index % 4 == 0
            schedule = Product.RegulatorySchedule.H if is_rx else Product.RegulatorySchedule.NONE
            safety = Product.SafetyClassification.PRESCRIPTION if is_rx else Product.SafetyClassification.OTC
            mrp = Decimal(str(80 + ((index * 37) % 9500))).quantize(Decimal("0.01"))
            selling = (mrp * Decimal("0.82")).quantize(Decimal("0.01"))
            name = f"{DEMO} {product_type.replace('_', ' ').title()} {index:04d}"
            sku = f"MM-DEMO-{index:06d}"
            product, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "slug": f"medimart-demo-{index:04d}",
                    "category": categories[(index - 1) % len(categories)],
                    "brand": brands[(index - 1) % len(brands)],
                    "product_type": product_type,
                    "image": self.image_path(index),
                    "short_description": f"Synthetic {product_type.replace('_', ' ')} catalogue item for QA.",
                    "description": "DEMO DATA. Verify all clinical, regulatory, tax, seller, and packaging information before production.",
                    "mrp": mrp,
                    "selling_price": selling,
                    "stock_quantity": 100 + (index % 400),
                    "requires_prescription": is_rx,
                    "requires_business_license": is_medicine,
                    "required_license_type": Product.RegulationType.DRUG_SALE if is_medicine else Product.RegulationType.NONE,
                    "regulatory_classification": "DEMO catalogue classification",
                    "regulatory_notes": "Synthetic local-development record; manual compliance review required.",
                    "regulatory_schedule": schedule,
                    "state_restrictions": [],
                    "requires_pharmacist_review": is_rx,
                    "safety_classification": safety,
                    "quantity_limit_per_order": 2 if is_rx else 0,
                    "minimum_shelf_life_days": 90 if is_medicine else 0,
                    "cold_chain_required": is_medicine and index % 17 == 0,
                    "barcode": f"890000{index:07d}",
                    "manufacturer": f"MediMart Demo Manufacturing Unit {index % 12 + 1}",
                    "composition": f"Demo active ingredient {index:04d}" if is_medicine else "",
                    "pack_size": "Strip of 10" if is_medicine else "Pack of 1",
                    "unit": "tablet" if is_medicine else "piece",
                    "seo_title": f"{name} | MediMart",
                    "seo_description": f"Synthetic catalogue listing for {name}.",
                    "is_active": True,
                    "is_featured": index % 20 == 0,
                },
            )
            products.append(product)
            if is_medicine:
                medicines.append(product)

            for image_index in range(2):
                ProductImage.objects.get_or_create(
                    product=product,
                    alt_text=f"{DEMO} image {image_index + 1} for {name}",
                    defaults={"image": self.image_path(index + image_index), "is_primary": image_index == 0},
                )
            for spec_name, spec_value in (
                ("Pack size", "Synthetic demo pack"),
                ("Storage", "Store according to verified label instructions"),
                ("Catalogue status", "DEMO - replace before production"),
            ):
                ProductSpecification.objects.get_or_create(
                    product=product,
                    name=spec_name,
                    defaults={"value": spec_value},
                )
            ProductVariant.objects.get_or_create(
                sku=f"{sku}-V1",
                defaults={
                    "product": product,
                    "pack_size": "Standard demo pack",
                    "strength": "500 mg" if is_medicine else "Standard",
                    "dosage_form": "Tablet" if is_medicine else "Unit",
                    "flavour": "Unflavoured",
                    "form": "Standard",
                    "colour": "White",
                    "mrp": mrp,
                    "selling_price": selling,
                    "stock_quantity": 40,
                    "is_active": True,
                    "is_approved": True,
                },
            )

            if is_medicine:
                ProductClinicalProfile.objects.update_or_create(
                    product=product,
                    defaults={
                        "active_ingredient": f"Demo ingredient {index:04d}",
                        "strength": "500 mg",
                        "dosage_form": "Tablet",
                        "route": "Oral",
                        "therapeutic_class": "Synthetic catalogue class",
                        "chemical_class": "Synthetic catalogue chemical class",
                        "action_class": "Demo action class",
                        "uses": "DEMO only. Clinical content must be reviewed before publication.",
                        "benefits": "No production clinical claim.",
                        "dosage_information": "Follow the approved label and clinician instructions.",
                        "safety_advice": "Do not self-prescribe. Consult a qualified clinician.",
                        "pregnancy_advice": "Ask a qualified clinician.",
                        "kidney_advice": "Ask a qualified clinician.",
                        "liver_advice": "Ask a qualified clinician.",
                        "alcohol_advice": "Ask a qualified clinician.",
                        "storage_instructions": "Follow verified packaging instructions.",
                        "marketer": "MediMart Demo Healthcare",
                        "country_of_origin": "India",
                        "manufacturing_license": "DEMO-REPLACE-MANUFACTURING-LICENCE",
                        "gst_hsn_code": "3004-DEMO",
                        "content_sources": "DEMO DATA - clinical review required",
                        "last_reviewed_at": timezone.now(),
                        "review_due_at": timezone.now() + timedelta(days=90),
                        "review_status": ProductClinicalProfile.ReviewStatus.PUBLISHED,
                        "reviewed_by": self.first_or_none(pharmacists) or admin,
                        "reviewed_at": timezone.now(),
                    },
                )

        for index, product in enumerate(medicines[: max(0, len(medicines) - 1)]):
            related = medicines[index + 1]
            ClinicalInteraction.objects.get_or_create(
                product=product,
                related_product=related,
                trigger="DEMO interaction review",
                defaults={
                    "interaction_type": "drug-drug",
                    "severity": "moderate",
                    "guidance": "Synthetic interaction record. Pharmacist review required.",
                    "source_reference": "DEMO-CLINICAL-REVIEW",
                    "reviewed_by": self.first_or_none(pharmacists) or admin,
                    "reviewed_at": timezone.now(),
                    "is_published": True,
                },
            )
        return products, medicines

    def seed_sellers(self, products, admin, compliance_users):
        vendor_users = self.get_users(UserProfile.Role.VENDOR)
        manufacturer_users = self.get_users(UserProfile.Role.MANUFACTURER)
        pharmacy_users = self.get_users(UserProfile.Role.PHARMACY)
        seller_rows = []
        for role, users, business_type in (
            ("vendor", vendor_users, Vendor.BusinessType.GENERAL_HEALTHCARE),
            ("manufacturer", manufacturer_users, Vendor.BusinessType.MANUFACTURER),
            ("pharmacy", pharmacy_users, Vendor.BusinessType.PHARMACY),
        ):
            for index, user in enumerate(users, start=1):
                seller, _ = Vendor.objects.update_or_create(
                    user=user,
                    defaults={
                        "business_name": f"{DEMO} {role.title()} {index:02d}",
                        "owner_name": user.get_full_name() or user.username,
                        "email": user.email,
                        "phone": getattr(user.profile, "phone_number", "9000000000"),
                        "address": f"{DEMO} business address {index}, Ahmedabad, Gujarat",
                        "gst_number": f"DEMO-GST-{role.upper()}-{index:03d}",
                        "license_number": f"DEMO-{role.upper()}-LIC-{index:04d}",
                        "business_type": business_type,
                        "bank_name": "DEMO BANK",
                        "bank_account_number": f"DEMO-ACCOUNT-{index:04d}",
                        "ifsc_code": "DEMO0000001",
                        "is_approved": True,
                        "is_active": True,
                    },
                )
                license_type = (
                    BusinessLicense.LicenseType.DRUG_RETAIL
                    if role == "pharmacy"
                    else BusinessLicense.LicenseType.DEVICE_MANUFACTURING
                    if role == "manufacturer"
                    else BusinessLicense.LicenseType.OTHER
                )
                BusinessLicense.objects.update_or_create(
                    vendor=seller,
                    license_type=license_type,
                    license_number=seller.license_number,
                    defaults={
                        "legal_name": seller.business_name,
                        "premises_address": seller.address,
                        "state": "Gujarat",
                        "licensing_authority": "DEMO - replace with verified authority",
                        "issued_on": date.today() - timedelta(days=180),
                        "valid_until": date.today() + timedelta(days=365),
                        "status": BusinessLicense.Status.VERIFIED,
                        "verification_source": BusinessLicense.VerificationSource.APPLICANT,
                        "reviewed_by": self.first_or_none(compliance_users) or admin,
                        "reviewed_at": timezone.now(),
                        "review_notes": "DEMO DATA ONLY. Replace with real evidence and compliance decision.",
                    },
                )
                seller_rows.append(seller)

        offers = []
        for index, product in enumerate(products):
            compatible = [seller for seller in seller_rows if seller.business_type == Vendor.BusinessType.PHARMACY] if product.product_type == Product.ProductType.MEDICINE else seller_rows
            for offset in range(min(3, len(compatible))):
                seller = compatible[(index + offset) % len(compatible)]
                price = (product.selling_price + Decimal(str(offset * 3))).quantize(Decimal("0.01"))
                offer, _ = VendorProduct.objects.update_or_create(
                    vendor=seller,
                    product=product,
                    defaults={
                        "price": min(price, product.mrp),
                        "stock_quantity": 20 + ((index + offset) % 80),
                        "delivery_time": f"{1 + offset}-{3 + offset} days",
                        "warranty": "DEMO warranty policy",
                        "offer_text": "DEMO approved seller offer - replace before production",
                        "seller_rating": Decimal("4.50"),
                        "is_active": True,
                        "is_approved": True,
                    },
                )
                offers.append(offer)
        return seller_rows, offers

    def seed_staff_profiles(self, admin):
        for index, user in enumerate(self.get_users(UserProfile.Role.DOCTOR), start=1):
            DoctorProfile.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": user.get_full_name() or user.username,
                    "specialization": ["General Medicine", "Dermatology", "Cardiology", "Pediatrics"][index % 4],
                    "registration_number": f"DEMO-MCI-{index:05d}",
                    "medical_council": "DEMO Medical Council - replace before production",
                    "qualification": "MBBS (DEMO RECORD)",
                    "experience_years": 2 + index % 18,
                    "clinic_name": f"{DEMO} Care Clinic {index:02d}",
                    "clinic_address": f"{index} {DEMO} Health Avenue, Ahmedabad, Gujarat",
                    "phone": getattr(user.profile, "phone_number", "9000000000"),
                    "consultation_fee": Decimal(str(299 + (index % 8) * 100)),
                    "availability": "Mon-Sat, 10:00-18:00",
                    "is_verified": True,
                    "verified_by": admin,
                    "verified_at": timezone.now(),
                },
            )
        for index, user in enumerate(self.get_users(UserProfile.Role.PHARMACIST), start=1):
            PharmacistProfile.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": user.get_full_name() or user.username,
                    "registration_number": f"DEMO-PH-{index:05d}",
                    "licensing_authority": "DEMO Pharmacy Council - replace before production",
                    "pharmacy_name": f"{DEMO} Pharmacy {index:02d}",
                    "pharmacy_license_number": f"DEMO-PHARM-LIC-{index:04d}",
                    "state": "Gujarat",
                    "is_verified": True,
                    "verified_by": admin,
                    "verified_at": timezone.now(),
                },
            )

    def seed_inventory(self, offers, admin):
        warehouses = []
        for index in range(1, 7):
            warehouse, _ = Warehouse.objects.get_or_create(
                code=f"DEMO-WH-{index:02d}",
                defaults={
                    "name": f"{DEMO} Fulfilment Hub {index:02d}",
                    "address": f"{index} {DEMO} Logistics Park, Ahmedabad, Gujarat",
                    "pincode": f"3800{index:02d}",
                    "is_active": True,
                },
            )
            warehouses.append(warehouse)
        batches = []
        for index, offer in enumerate(offers):
            warehouse = warehouses[index % len(warehouses)]
            batch_number = f"DEMO-BATCH-{offer.id:06d}"
            is_cold = offer.product.cold_chain_required
            batch, _ = InventoryBatch.objects.update_or_create(
                vendor_product=offer,
                warehouse=warehouse,
                batch_number=batch_number,
                defaults={
                    "manufactured_on": date.today() - timedelta(days=45),
                    "expires_on": date.today() + timedelta(days=365),
                    "quantity": 100,
                    "reserved_quantity": 0,
                    "mrp": offer.product.mrp,
                    "supplier_name": f"{DEMO} Supplier {index % 20 + 1:02d}",
                    "supplier_invoice_number": f"DEMO-INV-{index:07d}",
                    "dispensing_pharmacy": offer.vendor.business_name if offer.product.product_type == Product.ProductType.MEDICINE else "",
                    "storage_min_celsius": Decimal("2.00") if is_cold else Decimal("15.00"),
                    "storage_max_celsius": Decimal("8.00") if is_cold else Decimal("30.00"),
                    "excursion_status": "normal",
                    "temperature_log": [],
                },
            )
            batches.append(batch)
            InventoryMovement.objects.get_or_create(
                batch=batch,
                movement_type=InventoryMovement.MovementType.RECEIPT,
                reference=f"DEMO-RECEIPT-{batch.id}",
                defaults={"quantity": 100, "actor": admin},
            )
            if is_cold:
                InventoryTemperatureLog.objects.get_or_create(
                    batch=batch,
                    source="DEMO sensor",
                    defaults={
                        "temperature_celsius": Decimal("5.00"),
                        "recorded_by": admin,
                        "note": "Synthetic normal cold-chain reading.",
                    },
                )
        return warehouses, batches

    def seed_customers(self, products, admin):
        customers = self.get_users(UserProfile.Role.CUSTOMER)
        addresses = []
        dependents = []
        for user_index, user in enumerate(customers):
            for address_index in range(1, 4):
                address, _ = Address.objects.get_or_create(
                    user=user,
                    full_name=f"{user.get_full_name() or user.username} {address_index}",
                    address_line_1=f"{address_index} {DEMO} Wellness Street",
                    city=["Ahmedabad", "Vadodara", "Surat"][user_index % 3],
                    pincode=f"3800{(user_index + address_index):02d}",
                    defaults={
                        "phone": getattr(user.profile, "phone_number", "9000000000"),
                        "state": "Gujarat",
                        "country": "India",
                        "address_type": "home" if address_index == 1 else "other",
                        "is_default": address_index == 1,
                    },
                )
                addresses.append(address)
            for dependent_index, relationship in enumerate(("spouse", "child", "parent"), start=1):
                dependent, _ = Dependent.objects.get_or_create(
                    user=user,
                    full_name=f"{DEMO} {user_index + 1} Dependent {dependent_index}",
                    date_of_birth=date(1985 + dependent_index, 1, 10 + user_index),
                    defaults={
                        "relationship": relationship,
                        "gender": "other",
                        "phone": getattr(user.profile, "phone_number", "9000000000"),
                        "consent_at": timezone.now(),
                        "is_active": True,
                    },
                )
                dependents.append(dependent)
            Cart.objects.get_or_create(user=user)
            wishlist, _ = Wishlist.objects.get_or_create(user=user)
            for product in products[user_index:: max(1, len(customers))][:10]:
                WishlistItem.objects.get_or_create(wishlist=wishlist, product=product)
        return customers, addresses, dependents

    def seed_prescriptions(self, customers, medicines, doctors, pharmacists):
        if not medicines or not customers:
            return []
        file_path = self.demo_file(
            "demo-prescription.pdf",
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n",
        )
        prescriptions = []
        reviewer = self.first_or_none(pharmacists)
        doctor = self.first_or_none(doctors)
        for index in range(1, 601):
            customer = customers[(index - 1) % len(customers)]
            medicine = medicines[(index - 1) % len(medicines)]
            marker = f"{DEMO}-PRESCRIPTION-{index:05d}"
            prescription = Prescription.objects.filter(user=customer, notes=marker).first()
            if not prescription:
                status = [Prescription.Status.APPROVED, Prescription.Status.PARTIALLY_APPROVED, Prescription.Status.NEEDS_INFORMATION][index % 3]
                prescription = Prescription.objects.create(
                    user=customer,
                    file=file_path,
                    patient_name=customer.get_full_name() or customer.username,
                    patient_date_of_birth=date(1990 + (index % 20), 3, 12),
                    patient_gender=Prescription.PatientGender.OTHER,
                    doctor_name=doctor.full_name if doctor else "DEMO Doctor",
                    doctor_registration_number=f"DEMO-MCI-{index % 20 + 1:05d}",
                    clinic_name="DEMO Clinic - replace before production",
                    clinic_contact="9000000000",
                    prescription_date=date.today() - timedelta(days=index % 30),
                    valid_until=date.today() + timedelta(days=90),
                    max_fulfillments=2,
                    requested_medicines=medicine.name,
                    notes=marker,
                    customer_consent=True,
                    status=status,
                    clarification_message="Please confirm dosage details." if status == Prescription.Status.NEEDS_INFORMATION else "",
                    scan_status=Prescription.ScanStatus.COMPLETE,
                    scan_summary="DEMO technical scan result; human review required.",
                    scan_flags=[],
                    scan_completed_at=timezone.now(),
                    prescriber_verified=True,
                    patient_identity_verified=True,
                    clinical_validation_status="passed" if status != Prescription.Status.NEEDS_INFORMATION else "needs_information",
                    validation_flags=[] if status != Prescription.Status.NEEDS_INFORMATION else ["dosage_confirmation_required"],
                    reviewed_by=reviewer,
                    reviewed_at=timezone.now(),
                )
                item_status = PrescriptionItem.ApprovalStatus.APPROVED if status == Prescription.Status.APPROVED else PrescriptionItem.ApprovalStatus.CLARIFICATION if status == Prescription.Status.NEEDS_INFORMATION else PrescriptionItem.ApprovalStatus.APPROVED
                item = PrescriptionItem.objects.create(
                    prescription=prescription,
                    product=medicine,
                    prescribed_name=medicine.name,
                    dosage="One tablet twice daily",
                    duration_days=7,
                    instructions="DEMO instructions; verify against the original prescription.",
                    quantity=10,
                    approval_status=item_status,
                    review_note="DEMO pharmacist review",
                    reviewed_by=reviewer,
                    reviewed_at=timezone.now(),
                )
                PrescriptionReview.objects.create(
                    prescription=prescription,
                    reviewer=reviewer or customer,
                    decision="approved" if item_status == PrescriptionItem.ApprovalStatus.APPROVED else "clarification",
                    pharmacy_license_number="DEMO-PHARM-LIC-0001",
                    notes="DEMO decision; replace with a real pharmacist decision.",
                    validation_snapshot={"demo": True, "item_id": item.id},
                )
            prescriptions.append(prescription)
        return prescriptions

    def seed_product_trust_records(self, products, medicines, customers, pharmacists, sellers):
        if customers:
            for index, product in enumerate(products):
                customer = customers[index % len(customers)]
                ProductQuestion.objects.get_or_create(
                    product=product,
                    user=customer,
                    question=f"{DEMO} question about product {product.sku}",
                    defaults={
                        "answer": "Synthetic catalogue answer for local QA. Confirm product information with the approved seller.",
                        "status": "answered",
                        "answered_by": self.first_or_none(sellers).user if sellers else None,
                        "answered_at": timezone.now(),
                    },
                )
        if len(medicines) > 1:
            reviewer = self.first_or_none(pharmacists)
            for index, product in enumerate(medicines[:-1]):
                substitute = medicines[index + 1]
                ProductSubstitute.objects.get_or_create(
                    product=product,
                    substitute=substitute,
                    defaults={
                        "status": ProductSubstitute.Status.APPROVED,
                        "rationale": "Synthetic pharmacist-reviewed substitute for local workflow testing.",
                        "approved_by": reviewer,
                        "approved_at": timezone.now(),
                    },
                )

    def seed_orders(self, order_count, customers, addresses, offers, products, delivery_staff, coupons):
        safe_offers = [offer for offer in offers if not offer.product.requires_prescription and offer.product.is_active]
        if not customers or not addresses or not safe_offers:
            return [], []
        orders = []
        order_items = []
        status_history = []
        payments = []
        breakdowns = []
        shipments = []
        for index in range(1, order_count + 1):
            customer = customers[(index - 1) % len(customers)]
            address = next(address for address in addresses if address.user_id == customer.id and address.is_default)
            offer = safe_offers[(index - 1) % len(safe_offers)]
            quantity = 1 + index % 3
            subtotal = (offer.price * quantity).quantize(Decimal("0.01"))
            discount = Decimal("50.00") if index % 10 == 0 and subtotal >= 250 else Decimal("0.00")
            delivery_charge = Decimal("0.00") if subtotal >= 999 else Decimal("49.00")
            total = subtotal - discount + delivery_charge
            status_cycle = [Order.OrderStatus.DELIVERED, Order.OrderStatus.SHIPPED, Order.OrderStatus.PROCESSING, Order.OrderStatus.CANCELLED]
            order_status = status_cycle[index % len(status_cycle)]
            payment_method = Order.PaymentMethod.COD if index % 5 == 0 else Order.PaymentMethod.RAZORPAY
            payment_status = Order.PaymentStatus.PAID if order_status not in {Order.OrderStatus.CANCELLED} else Order.PaymentStatus.FAILED
            order_number = f"MMDEMO{index:08d}"
            order, _ = Order.objects.get_or_create(
                order_number=order_number,
                defaults={
                    "customer": customer,
                    "address": address,
                    "delivery_staff": delivery_staff[(index - 1) % len(delivery_staff)] if delivery_staff else None,
                    "address_snapshot": f"{address.full_name}, {address.address_line_1}, {address.city}, {address.pincode}",
                    "subtotal": subtotal,
                    "discount": discount,
                    "delivery_charge": delivery_charge,
                    "total_amount": total,
                    "coupon": coupons[index % len(coupons)] if coupons and index % 10 == 0 else None,
                    "payment_method": payment_method,
                    "payment_status": payment_status,
                    "order_status": order_status,
                },
            )
            item, _ = OrderItem.objects.get_or_create(
                order=order,
                vendor_product=offer,
                defaults={
                    "vendor": offer.vendor,
                    "product": offer.product,
                    "product_name": offer.product.name,
                    "seller_name": offer.vendor.business_name,
                    "sku": offer.product.sku,
                    "quantity": quantity,
                    "unit_price": offer.price,
                    "total_price": subtotal,
                },
            )
            orders.append(order)
            order_items.append(item)
            for status in (Order.OrderStatus.PENDING, Order.OrderStatus.CONFIRMED, Order.OrderStatus.PROCESSING, order_status):
                OrderStatusHistory.objects.get_or_create(order=order, status=status, defaults={"note": f"{DEMO} lifecycle event", "actor": delivery_staff[0] if delivery_staff else None})
            Payment.objects.get_or_create(
                order=order,
                defaults={
                    "payment_method": payment_method,
                    "amount": total,
                    "status": payment_status,
                    "captured_amount": total if payment_status == Order.PaymentStatus.PAID else Decimal("0.00"),
                    "gateway_order_id": f"demo_gateway_order_{index:08d}" if payment_method == Order.PaymentMethod.RAZORPAY else None,
                    "transaction_id": f"DEMO-TXN-{index:08d}",
                    "gateway_status": "demo_captured" if payment_status == Order.PaymentStatus.PAID else "demo_failed",
                    "gateway_metadata": {"demo": True},
                    "verified_at": timezone.now() if payment_status == Order.PaymentStatus.PAID else None,
                },
            )
            OrderChargeBreakdown.objects.get_or_create(
                order=order,
                defaults={
                    "subtotal": subtotal,
                    "discount": discount,
                    "tax_amount": (subtotal * Decimal("0.05")).quantize(Decimal("0.01")),
                    "handling_charge": Decimal("10.00"),
                    "platform_fee": Decimal("5.00"),
                    "delivery_charge": delivery_charge,
                    "cold_chain_charge": Decimal("0.00"),
                    "total_amount": total,
                },
            )
            if payment_status == Order.PaymentStatus.PAID:
                PaymentReconciliation.objects.get_or_create(
                    payment=order.payment,
                    provider_reference=f"DEMO-REC-{index:08d}",
                    defaults={
                        "provider_status": "captured",
                        "gateway_amount": total,
                        "expected_amount": total,
                        "status": "matched",
                        "reconciled_by": delivery_staff[0] if delivery_staff else None,
                        "reconciled_at": timezone.now(),
                    },
                )
            if order_status in {Order.OrderStatus.SHIPPED, Order.OrderStatus.DELIVERED}:
                shipment, _ = Shipment.objects.get_or_create(
                    order=order,
                    defaults={
                        "warehouse": None,
                        "courier_name": "DEMO Courier",
                        "tracking_number": f"DEMO-TRK-{index:08d}",
                        "status": "delivered" if order_status == Order.OrderStatus.DELIVERED else "in_transit",
                        "promised_at": timezone.now() + timedelta(days=2),
                        "shipped_at": timezone.now() - timedelta(days=1),
                        "delivered_at": timezone.now() if order_status == Order.OrderStatus.DELIVERED else None,
                        "delivery_recipient_name": address.full_name,
                    },
                )
                shipments.append(shipment)
                for shipment_status in ("booked", "in_transit", "out_for_delivery", "delivered")[: (4 if order_status == Order.OrderStatus.DELIVERED else 2)]:
                    ShipmentEvent.objects.get_or_create(shipment=shipment, status=shipment_status, defaults={"location": address.city, "description": f"{DEMO} shipment event"})
        for coupon in coupons:
            for order in orders[: min(6, len(orders))]:
                if order.customer_id and order.coupon_id == coupon.id:
                    CouponUsage.objects.get_or_create(coupon=coupon, user_id=order.customer_id, order=order)
        return orders, order_items

    def seed_reviews_and_support(self, review_count, customers, products, order_items, sellers, support_users):
        if not customers or not products:
            return
        reviews = []
        seen = set()
        for item in order_items:
            key = (item.order.customer_id, item.product_id)
            if key in seen:
                continue
            seen.add(key)
            review, _ = Review.objects.get_or_create(
                user_id=item.order.customer_id,
                product=item.product,
                defaults={
                    "order_item": item,
                    "rating": 3 + (item.id % 3),
                    "title": f"{DEMO} customer review {item.id}",
                    "comment": "Synthetic review for local catalogue and moderation testing.",
                    "is_approved": True,
                },
            )
            reviews.append(review)
            if len(reviews) >= review_count:
                break
        for review in reviews:
            for voter in customers[:2]:
                ReviewHelpfulVote.objects.get_or_create(review=review, user=voter, defaults={"is_helpful": True})
            seller = self.first_or_none(sellers)
            if seller:
                ReviewSellerReply.objects.get_or_create(
                    review=review,
                    defaults={"seller": seller.user, "reply": "DEMO seller reply for moderation testing.", "is_published": True},
                )
        if not self.marker_exists(SupportTicket, "subject", f"{DEMO} Support"):
            tickets = []
            messages = []
            for index in range(1, 501):
                customer = customers[(index - 1) % len(customers)]
                ticket = SupportTicket(
                    user=customer,
                    subject=f"{DEMO} Support ticket {index:04d}",
                    category=["order", "product", "payment", "account"][index % 4],
                    message="Synthetic customer support request for workflow testing.",
                    order_number=f"MMDEMO{index:08d}",
                    status="resolved" if index % 3 else "open",
                )
                tickets.append(ticket)
            self.bulk(SupportTicket, tickets)
            for ticket in SupportTicket.objects.filter(subject__startswith=f"{DEMO} Support").iterator():
                messages.append(SupportMessage(ticket=ticket, sender=self.first_or_none(support_users) or ticket.user, message="DEMO support response.", is_staff_reply=True))
                if len(messages) >= 1000:
                    break
            self.bulk(SupportMessage, messages)

    def seed_returns_and_finance(self, orders, order_items, support_users, operations_users):
        completed_items = [item for item in order_items if item.order.order_status == Order.OrderStatus.DELIVERED]
        reviewer = self.first_or_none(support_users) or self.first_or_none(operations_users)
        warehouse_actor = self.first_or_none(operations_users) or reviewer
        for index, item in enumerate(completed_items[:150], start=1):
            marker = f"{DEMO}-RETURN-{index:05d}"
            return_request = ReturnRequest.objects.filter(order_item=item, description=marker).first()
            if return_request:
                continue
            amount = item.total_price
            return_request = ReturnRequest.objects.create(
                order_item=item,
                user=item.order.customer,
                reason=["damaged", "wrong_item", "quality", "missing"][index % 4],
                quantity=1,
                description=marker,
                status="completed" if index % 3 else "under_review",
                approved_at=timezone.now() if index % 3 else None,
                pickup_scheduled_at=timezone.now() + timedelta(days=1) if index % 3 else None,
                pickup_reference=f"DEMO-PICKUP-{index:05d}" if index % 3 else "",
                received_at=timezone.now() if index % 3 else None,
                inspection_decision="restocked" if index % 2 else "accepted",
                inspected_by=warehouse_actor,
                inspected_at=timezone.now() if index % 3 else None,
                refund_amount=amount,
                resolution_note="Synthetic return workflow record for local QA.",
                reviewed_by=reviewer,
            )
            if index % 3:
                Refund.objects.create(
                    payment=item.order.payment,
                    return_request=return_request,
                    amount=amount,
                    reason="DEMO return refund",
                    status="completed",
                    gateway_refund_id=f"DEMO-REFUND-{index:05d}",
                    requested_by=item.order.customer,
                )
                CreditNote.objects.create(
                    order=item.order,
                    amount=amount,
                    reason=f"{DEMO} return credit note {index:05d}",
                    status="issued",
                    issued_by=reviewer,
                    issued_at=timezone.now(),
                )

        for index in range(1, 31):
            PaymentSettlement.objects.get_or_create(
                settlement_reference=f"{DEMO}-SETTLEMENT-{index:04d}",
                defaults={
                    "provider": "demo_razorpay",
                    "settlement_date": date.today() - timedelta(days=index),
                    "gross_amount": Decimal("100000.00"),
                    "fee_amount": Decimal("2000.00"),
                    "tax_amount": Decimal("360.00"),
                    "net_amount": Decimal("97640.00"),
                    "status": "received" if index % 3 else "exception",
                    "notes": "DEMO settlement. Replace with real gateway reconciliation.",
                },
            )

    def seed_healthcare(self, customers, dependents, doctors, lab_staff, products):
        demo_image = self.image_path(0)
        partners = []
        for index in range(1, 11):
            partner, _ = LabPartner.objects.update_or_create(
                name=f"{DEMO} Diagnostics Partner {index:02d}",
                city=["Ahmedabad", "Vadodara", "Surat", "Rajkot"][index % 4],
                defaults={
                    "address": f"{index} {DEMO} Diagnostic Road, Gujarat",
                    "accreditations": "DEMO accreditation - replace before production",
                    "licence_number": f"DEMO-LAB-LIC-{index:04d}",
                    "operating_hours": "07:00-20:00",
                    "service_area_pincodes": [f"3800{index:02d}"],
                    "website": "https://example.invalid/demo-lab",
                    "phone": "9000000000",
                    "is_active": True,
                },
            )
            partners.append(partner)
            for branch_index in range(1, 4):
                LabBranch.objects.get_or_create(
                    partner=partner,
                    name=f"{DEMO} Branch {index:02d}-{branch_index:02d}",
                    defaults={
                        "address": f"{branch_index} {DEMO} Collection Centre",
                        "city": partner.city,
                        "pincode": f"380{index:03d}",
                        "phone": "9000000000",
                        "operating_hours": "07:00-20:00",
                        "service_area_pincodes": [f"380{index:03d}"],
                        "is_active": True,
                    },
                )
        tests = []
        for index in range(1, 101):
            partner = partners[(index - 1) % len(partners)]
            test, _ = LabTest.objects.update_or_create(
                partner=partner,
                name=f"{DEMO} Lab Test {index:03d}",
                defaults={
                    "image": demo_image,
                    "category": "test" if index % 3 else "package",
                    "description": "Synthetic lab catalogue record for booking and reporting QA.",
                    "sample_type": "Blood",
                    "preparation": "Follow the verified partner instructions.",
                    "what_it_measures": "DEMO measurement description.",
                    "limitations": "Synthetic record; not medical advice.",
                    "included_test_count": 1 + index % 6,
                    "report_sla_hours": 24 + index % 48,
                    "price": Decimal(str(199 + (index % 15) * 50)),
                    "mrp": Decimal(str(299 + (index % 15) * 60)),
                    "is_home_collection": True,
                    "is_active": True,
                },
            )
            tests.append(test)
            for sex in ("any", "male", "female"):
                LabReferenceRange.objects.get_or_create(
                    lab_test=test,
                    test_name=f"Analyte {index:03d}",
                    sex=sex,
                    min_age_years=0,
                    max_age_years=120,
                    defaults={
                        "range_text": "DEMO range - verify with partner",
                        "unit": "unit",
                        "source_note": "DEMO data only",
                        "reviewed_by": self.first_or_none(lab_staff),
                        "reviewed_at": timezone.now(),
                        "is_active": True,
                    },
                )
        slots = []
        for index in range(1, 301):
            partner = partners[(index - 1) % len(partners)]
            start = timezone.now() + timedelta(days=index % 30, hours=7 + index % 10)
            slot, _ = LabCollectionSlot.objects.get_or_create(
                partner=partner,
                starts_at=start,
                defaults={"ends_at": start + timedelta(hours=1), "capacity": 8, "booked_count": 0, "is_blackout": False, "is_active": True},
            )
            slots.append(slot)
        for index in range(1, 601):
            if not customers or not tests or not slots:
                break
            customer = customers[(index - 1) % len(customers)]
            test = tests[(index - 1) % len(tests)]
            slot = slots[(index - 1) % len(slots)]
            marker = f"{DEMO}-LAB-BOOKING-{index:05d}"
            booking = LabBooking.objects.filter(accession_number=marker).first()
            if booking:
                continue
            booking_status = "report_ready" if index % 4 == 0 else "sample_collected" if index % 3 == 0 else "confirmed"
            booking = LabBooking.objects.create(
                user=customer,
                dependent=dependents[(index - 1) % len(dependents)] if dependents else None,
                lab_test=test,
                slot=slot,
                phlebotomist=self.first_or_none(lab_staff),
                address=Address.objects.filter(user=customer, is_default=True).first(),
                status=booking_status,
                scheduled_start=slot.starts_at,
                scheduled_end=slot.ends_at,
                collection_otp="123456",
                identity_verified_at=timezone.now(),
                sample_collected_at=timezone.now() if booking_status != "confirmed" else None,
                accession_number=marker,
                report_summary="DEMO non-diagnostic report summary." if booking_status == "report_ready" else "",
                report_ready_at=timezone.now() if booking_status == "report_ready" else None,
            )
            for event_type in ("requested", "collected", "received_at_lab", "processing")[: (4 if booking_status == "report_ready" else 2)]:
                LabSampleEvent.objects.create(booking=booking, event_type=event_type, barcode=f"DEMO-BARCODE-{booking.id:06d}", location=partner.city if (partner := test.partner) else "DEMO LAB", note="Synthetic chain-of-custody event", recorded_by=self.first_or_none(lab_staff))
            LabReportValue.objects.create(booking=booking, test_name=f"Analyte {index:03d}", value=str(4 + index % 8), unit="unit", reference_range="DEMO range", abnormal_flag="" if index % 5 else "review", medically_reviewed=booking_status == "report_ready", explanation="Synthetic non-diagnostic explanation.", explanation_reviewed_by=self.first_or_none(lab_staff), explanation_reviewed_at=timezone.now() if booking_status == "report_ready" else None)
            invoice = LabInvoice.objects.create(booking=booking, subtotal=test.price, tax_amount=(test.price * Decimal("0.05")).quantize(Decimal("0.01")), discount_amount=Decimal("0.00"), status="paid" if index % 4 else "issued", paid_at=timezone.now() if index % 4 else None)
            if index % 20 == 0:
                LabRefund.objects.create(invoice=invoice, amount=Decimal("50.00"), reason="DEMO cancellation/refund workflow", status="processed", reviewed_by=self.first_or_none(lab_staff), gateway_reference=f"DEMO-LAB-REF-{index:05d}")
            if index % 25 == 0:
                LabDispute.objects.create(booking=booking, raised_by=customer, category="report", description="DEMO lab dispute for operations testing.", status="resolved", resolution_note="DEMO resolution.", resolved_by=self.first_or_none(lab_staff))
        for index, partner in enumerate(partners, start=1):
            LabSettlement.objects.get_or_create(partner=partner, reference=f"DEMO-LAB-SETTLEMENT-{index:04d}", defaults={"period_start": date.today() - timedelta(days=30), "period_end": date.today(), "gross_amount": Decimal("25000.00"), "refund_amount": Decimal("500.00"), "platform_fee": Decimal("2500.00"), "net_amount": Decimal("22000.00"), "status": "paid", "notes": "DEMO settlement; replace with provider reconciliation."})

        doctor_profiles = list(DoctorProfile.objects.filter(user__profile__role=UserProfile.Role.DOCTOR))
        for doctor in doctor_profiles:
            for weekday in range(5):
                DoctorAvailability.objects.get_or_create(doctor=doctor, weekday=weekday, start_time=time(10, 0), defaults={"end_time": time(18, 0), "slot_minutes": 30, "capacity": 2, "is_active": True})
        for index in range(1, 601):
            if not customers or not doctor_profiles:
                break
            customer = customers[(index - 1) % len(customers)]
            doctor = doctor_profiles[(index - 1) % len(doctor_profiles)]
            marker = f"{DEMO}-CONSULTATION-{index:05d}"
            consultation = Consultation.objects.filter(symptoms=marker).first()
            if consultation:
                continue
            status = "completed" if index % 3 else "confirmed"
            consultation = Consultation.objects.create(user=customer, dependent=dependents[(index - 1) % len(dependents)] if dependents else None, doctor=doctor, mode=["chat", "audio", "video"][index % 3], status=status, symptoms=marker, patient_history="Synthetic history for QA.", allergies="No known allergies (DEMO)", current_medicines="Synthetic medicine list (DEMO)", red_flag_screening={"demo": True, "urgent_flags": []}, emergency_guidance="Seek emergency services for urgent symptoms.", fee=doctor.consultation_fee, consent_at=timezone.now(), scheduled_at=timezone.now() + timedelta(days=1), followup_until=timezone.now() + timedelta(days=30), clinical_notes="DEMO clinical note - replace with real doctor note.", advice="DEMO advice - replace with signed clinical advice.")
            ConsultationPayment.objects.create(consultation=consultation, amount=consultation.fee, status="paid", provider="demo_razorpay", provider_order_id=f"DEMO-CONSULT-ORDER-{index:05d}", provider_payment_id=f"DEMO-CONSULT-PAY-{index:05d}", paid_at=timezone.now())
            for message_index in range(3):
                ConsultationMessage.objects.create(consultation=consultation, sender=customer if message_index % 2 == 0 else doctor.user, message=f"{DEMO} consultation message {message_index + 1}.")
            ConsultationFollowUp.objects.create(consultation=consultation, scheduled_at=timezone.now() + timedelta(days=14), notes="DEMO follow-up.", status="scheduled", created_by=doctor.user)

        for index, customer in enumerate(customers, start=1):
            for reminder_index in range(1, 8):
                product = products[(index + reminder_index) % len(products)]
                MedicationReminder.objects.get_or_create(user=customer, label=f"{DEMO} reminder {index}-{reminder_index}", defaults={"dependent": dependents[(index + reminder_index) % len(dependents)] if dependents else None, "product": product, "dosage": "As directed", "frequency": "Daily", "next_due_at": timezone.now() + timedelta(hours=reminder_index), "is_active": True})
            for record_index in range(1, 5):
                HealthRecord.objects.get_or_create(user=customer, title=f"{DEMO} health record {index}-{record_index}", defaults={"dependent": dependents[(index + record_index) % len(dependents)] if dependents else None, "record_type": "lab_report", "provider_name": "DEMO Provider", "record_date": date.today() - timedelta(days=record_index * 30), "document": self.demo_file("demo-health-record.pdf", b"DEMO HEALTH RECORD - SYNTHETIC DATA"), "notes": "Synthetic record for local workflow testing."})

    def seed_notifications_and_content(self, notification_count, customers, staff, products):
        if not self.marker_exists(Notification, "title", f"{DEMO} Notification"):
            notifications = []
            for index in range(1, notification_count + 1):
                user = customers[(index - 1) % len(customers)] if customers else self.first_or_none(staff)
                if not user:
                    continue
                notifications.append(Notification(user=user, title=f"{DEMO} Notification {index:05d}", message="Synthetic in-app notification for QA.", notification_type="general", link="/notifications/", is_read=index % 4 == 0))
            self.bulk(Notification, notifications)
            deliveries = [NotificationDelivery(notification=notification, channel="email", destination=notification.user.email, status="sent", attempts=1, sent_at=timezone.now(), provider_reference=f"DEMO-EMAIL-{notification.id}") for notification in Notification.objects.filter(title__startswith=f"{DEMO} Notification")]
            self.bulk(NotificationDelivery, deliveries)

        category, _ = BlogCategory.objects.get_or_create(name=f"{DEMO} Health Guides", defaults={"description": "Synthetic health-guide category for local QA."})
        author = self.first_or_none(staff) or self.first_or_none(customers)
        for index in range(1, 31):
            BlogPost.objects.update_or_create(
                title=f"{DEMO} Health Guide {index:03d}",
                defaults={
                    "image": self.image_path(index),
                    "excerpt": "Synthetic guide excerpt for local content QA.",
                    "content": "DEMO CONTENT. Have qualified clinical and editorial reviewers approve health information before publication.",
                    "category": category,
                    "author": author,
                    "status": "published",
                    "reviewer_name": "DEMO Clinical Reviewer",
                    "reviewer_credentials": "Replace with verified credentials",
                    "source_references": "DEMO reference placeholder",
                    "last_reviewed_at": timezone.now(),
                    "review_due_at": timezone.now() + timedelta(days=90),
                },
            )
        for index in range(1, 1001):
            SearchQuery.objects.get_or_create(query=f"demo healthcare search {index:04d}", session_hash=f"demo-session-{index:04d}", defaults={"source": "catalogue", "result_count": index % 25, "lab_result_count": index % 7, "zero_result": index % 25 == 0, "user": customers[index % len(customers)] if customers else None})

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_role_accounts", verbosity=0)
        call_command("seed_products", verbosity=0)
        call_command("seed_vendors", verbosity=0)
        call_command("seed_healthcare", verbosity=0)
        call_command("seed_coupons", verbosity=0)

        admin = self.first_or_none(self.get_users(UserProfile.Role.ADMIN))
        compliance = self.get_users(UserProfile.Role.COMPLIANCE_OFFICER)
        pharmacists = self.get_users(UserProfile.Role.PHARMACIST)
        lab_staff = self.get_users(UserProfile.Role.PHLEBOTOMIST)
        doctors = list(DoctorProfile.objects.filter(user__profile__role=UserProfile.Role.DOCTOR))
        products, medicines = self.seed_catalogue(options["products"], admin, pharmacists)
        sellers, offers = self.seed_sellers(products, admin, compliance)
        self.seed_staff_profiles(admin)
        warehouses, batches = self.seed_inventory(offers, admin)
        customers, addresses, dependents = self.seed_customers(products, admin)
        self.seed_prescriptions(customers, medicines, doctors, pharmacists)
        self.seed_product_trust_records(products, medicines, customers, pharmacists, sellers)
        coupons = list(Coupon.objects.filter(is_active=True))
        delivery_staff = self.get_users(UserProfile.Role.DELIVERY_STAFF)
        orders, order_items = self.seed_orders(options["orders"], customers, addresses, offers, products, delivery_staff, coupons)
        self.seed_reviews_and_support(options["reviews"], customers, products, order_items, sellers, self.get_users(UserProfile.Role.SUPPORT_STAFF))
        self.seed_returns_and_finance(orders, order_items, self.get_users(UserProfile.Role.SUPPORT_STAFF), self.get_users(UserProfile.Role.OPERATIONS_MANAGER))
        self.seed_healthcare(customers, dependents, doctors, lab_staff, products)
        self.seed_notifications_and_content(options["notifications"], customers, self.get_users(UserProfile.Role.SUPPORT_STAFF) + compliance, products)

        audit_actors = [admin] + compliance + pharmacists + lab_staff
        audit_actors = [actor for actor in audit_actors if actor]
        if audit_actors and not self.marker_exists(AuditEvent, "action", f"{DEMO}."):
            events = [AuditEvent(actor=audit_actors[index % len(audit_actors)], action=f"{DEMO}.seed.record", target_type="demo", target_id=str(index), summary="Synthetic demo-data seed event.", metadata={"demo": True}) for index in range(1, 2001)]
            self.bulk(AuditEvent, events)

        # Keep seed markers private to the local-data command. Customer-facing
        # records are normalized into role-owned catalogue and workflow data.
        call_command("normalize_role_dataset", verbosity=0)
        call_command("finish_role_dataset_cleanup", verbosity=0)

        self.stdout.write(self.style.SUCCESS("Large MediMart demo dataset is ready."))
        self.stdout.write(f"Synthetic products: {Product.objects.filter(sku__startswith='MM-DEMO-').count()}")
        self.stdout.write(f"Synthetic orders: {Order.objects.filter(order_number__startswith='MMDEMO').count()}")
        self.stdout.write(f"Synthetic prescriptions: {Prescription.objects.filter(notes__startswith='DEMO-PRESCRIPTION-').count()}")
        self.stdout.write(f"Synthetic lab bookings: {LabBooking.objects.filter(accession_number__startswith='DEMO-LAB-').count()}")
        self.stdout.write(f"Synthetic consultations: {Consultation.objects.filter(symptoms__startswith='DEMO-CONSULTATION-').count()}")
        self.stdout.write("All generated records are synthetic local-development data and must be replaced or removed before production.")
