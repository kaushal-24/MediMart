from decimal import Decimal
from datetime import timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import Address, UserProfile
from cart.models import Cart, CartItem, Wishlist, WishlistItem
from extras.models import (
    BlogCategory,
    BlogPost,
    DoctorProfile,
    Notification,
    SupportMessage,
    SupportTicket,
)
from orders.models import Coupon, Order, OrderItem, OrderStatusHistory, Payment
from prescriptions.models import Prescription, PrescriptionItem
from products.models import Brand, Category, Product, ProductImage, ProductSpecification
from reviews.models import Review
from vendors.models import BusinessLicense, Vendor, VendorProduct


DEMO_PASSWORD = "MediMart@2026"


class Command(BaseCommand):
    help = "Delete all MediMart data, create demo users, seed demo data, download images, and write credentials."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm-reset",
            action="store_true",
            help="Confirm deletion of every record in the configured database.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo data reset is disabled when DEBUG=False.")
        if not options["confirm_reset"]:
            raise CommandError("This deletes all data. Re-run with --confirm-reset to continue.")
        self.stdout.write(self.style.WARNING("Deleting all existing MediMart database data..."))
        call_command("flush", interactive=False, verbosity=0)

        self.users = self.create_users()
        self.categories = self.create_categories()
        self.brands = self.create_brands()
        self.products = self.create_products()
        self.vendors = self.create_vendors_and_offers()
        self.create_customer_data()
        self.create_doctors()
        self.create_blog()
        self.create_support_and_notifications()
        self.write_credentials_file()

        self.stdout.write(self.style.SUCCESS("MediMart demo data reset complete."))
        self.stdout.write(self.style.SUCCESS("Credentials written to DEMO_CREDENTIALS.md."))

    def create_users(self):
        User = get_user_model()
        user_specs = [
            {
                "key": "admin",
                "username": "admin",
                "email": "admin@gmail.com",
                "first_name": "MediMart",
                "last_name": "Admin",
                "role": UserProfile.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "key": "customer",
                "username": "customer",
                "email": "customer@gmail.com",
                "first_name": "Aarav",
                "last_name": "Sharma",
                "role": UserProfile.Role.CUSTOMER,
            },
            {
                "key": "vendor",
                "username": "vendor",
                "email": "vendor@gmail.com",
                "first_name": "Riya",
                "last_name": "Kapoor",
                "role": UserProfile.Role.VENDOR,
            },
            {
                "key": "manufacturer",
                "username": "manufacturer",
                "email": "manufacturer@gmail.com",
                "first_name": "Dev",
                "last_name": "Iyer",
                "role": UserProfile.Role.MANUFACTURER,
            },
            {
                "key": "pharmacy",
                "username": "pharmacy",
                "email": "pharmacy@gmail.com",
                "first_name": "Kiran",
                "last_name": "Patel",
                "role": UserProfile.Role.PHARMACY,
            },
            {
                "key": "doctor",
                "username": "doctor",
                "email": "doctor@gmail.com",
                "first_name": "Ananya",
                "last_name": "Mehta",
                "role": UserProfile.Role.DOCTOR,
            },
            {
                "key": "delivery",
                "username": "delivery",
                "email": "delivery@gmail.com",
                "first_name": "Vikram",
                "last_name": "Singh",
                "role": UserProfile.Role.DELIVERY_STAFF,
            },
            {
                "key": "support",
                "username": "support",
                "email": "support@gmail.com",
                "first_name": "MediMart",
                "last_name": "Support",
                "role": UserProfile.Role.SUPPORT_STAFF,
            },
            {
                "key": "compliance",
                "username": "compliance",
                "email": "compliance@gmail.com",
                "first_name": "MediMart",
                "last_name": "Compliance",
                "role": UserProfile.Role.COMPLIANCE_OFFICER,
            },
            {
                "key": "catalog",
                "username": "catalog",
                "email": "catalog@gmail.com",
                "first_name": "MediMart",
                "last_name": "Catalog",
                "role": UserProfile.Role.CATALOG_MANAGER,
            },
            {
                "key": "operations",
                "username": "operations",
                "email": "operations@gmail.com",
                "first_name": "MediMart",
                "last_name": "Operations",
                "role": UserProfile.Role.OPERATIONS_MANAGER,
            },
            {
                "key": "warehouse",
                "username": "warehouse",
                "email": "warehouse@gmail.com",
                "first_name": "MediMart",
                "last_name": "Warehouse",
                "role": UserProfile.Role.WAREHOUSE_MANAGER,
            },
        ]

        users = {}
        for spec in user_specs:
            user = User.objects.create_user(
                username=spec["username"],
                email=spec["email"],
                password=DEMO_PASSWORD,
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                is_staff=spec.get("is_staff", False),
                is_superuser=spec.get("is_superuser", False),
            )
            UserProfile.objects.create(
                user=user,
                role=spec["role"],
                phone_number="9999999999",
            )
            users[spec["key"]] = user
        return users

    def create_categories(self):
        tree = {
            "Medicines": ["Pain Relief", "Antibiotics", "Diabetes Care"],
            "Medical Equipment": ["Blood Pressure Monitors", "Pulse Oximeters", "Nebulizers"],
            "Diagnostic Equipment": ["Glucometers", "Lab Equipment", "Thermometers"],
            "Surgical Equipment": ["Surgical Instruments", "Surgical Kits"],
            "Healthcare Products": ["First Aid", "Mobility Support"],
        }
        category_images = {
            "Medicines": "categories/medicines.webp",
            "Medical Equipment": "categories/medical-equipment.webp",
            "Diagnostic Equipment": "categories/diagnostic-equipment.webp",
            "Surgical Equipment": "categories/surgical-equipment.webp",
            "Healthcare Products": "categories/healthcare-products.webp",
        }
        categories = {}
        for parent_name, child_names in tree.items():
            parent = Category.objects.create(
                name=parent_name,
                slug=slugify(parent_name),
                description=f"{parent_name} available on MediMart.",
                image=category_images.get(parent_name, ""),
            )
            categories[parent_name] = parent
            for child_name in child_names:
                child = Category.objects.create(
                    name=child_name,
                    slug=slugify(child_name),
                    parent=parent,
                    description=f"Shop {child_name.lower()} on MediMart.",
                )
                categories[child_name] = child
        return categories

    def create_brands(self):
        brands = {}
        for name in ["LifeTrack", "MediSure", "CareMate", "SterilePro", "HealthPlus"]:
            brands[name] = Brand.objects.create(
                name=name,
                slug=slugify(name),
                description=f"{name} demo healthcare brand.",
            )
        return brands

    def create_products(self):
        product_specs = [
            {
                "name": "Digital Blood Pressure Monitor",
                "sku": "MM-BP-001",
                "category": "Blood Pressure Monitors",
                "brand": "LifeTrack",
                "type": Product.ProductType.MEDICAL_EQUIPMENT,
                "mrp": "2499.00",
                "price": "1799.00",
                "stock": 35,
                "short": "Automatic upper-arm BP monitor for home tracking.",
                "description": "Digital blood pressure monitor with large display, memory support, and easy one-touch operation.",
                "manufacturer": "LifeTrack Devices",
                "image": "Digital Blood Pressure Monitor.jpg",
                "specs": {"Display": "Digital LCD", "Cuff Size": "22-42 cm", "Warranty": "1 Year"},
            },
            {
                "name": "Fingertip Pulse Oximeter",
                "sku": "MM-PO-001",
                "category": "Pulse Oximeters",
                "brand": "MediSure",
                "type": Product.ProductType.MEDICAL_EQUIPMENT,
                "mrp": "1499.00",
                "price": "899.00",
                "stock": 48,
                "short": "Compact pulse oximeter for SpO2 and pulse readings.",
                "description": "Portable fingertip oximeter for quick oxygen saturation and pulse-rate checks.",
                "manufacturer": "MediSure Health",
                "image": "FingertipPulseOximeterMD300C2.jpg",
                "specs": {"Measures": "SpO2 and pulse rate", "Display": "OLED", "Warranty": "6 Months"},
            },
            {
                "name": "Glucometer Starter Kit",
                "sku": "MM-GL-001",
                "category": "Glucometers",
                "brand": "CareMate",
                "type": Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                "mrp": "1299.00",
                "price": "999.00",
                "stock": 22,
                "short": "Blood glucose monitor kit for home testing.",
                "description": "Home glucometer kit with memory support and fast readings.",
                "manufacturer": "CareMate Diagnostics",
                "image": "Glucometer002.jpg",
                "specs": {"Sample Type": "Capillary whole blood", "Result Time": "5 seconds", "Memory": "300 readings"},
            },
            {
                "name": "Compressor Nebulizer Machine",
                "sku": "MM-NB-001",
                "category": "Nebulizers",
                "brand": "MediSure",
                "type": Product.ProductType.MEDICAL_EQUIPMENT,
                "mrp": "2399.00",
                "price": "1699.00",
                "stock": 16,
                "short": "Compressor nebulizer for respiratory therapy support.",
                "description": "Compact nebulizer machine suitable for prescribed respiratory medicine delivery.",
                "manufacturer": "MediSure Health",
                "image": "Nebulizer.JPG",
                "specs": {"Medication Capacity": "6 ml", "Power": "230V AC", "Warranty": "1 Year"},
            },
            {
                "name": "Digital Clinical Thermometer",
                "sku": "MM-TH-001",
                "category": "Thermometers",
                "brand": "LifeTrack",
                "type": Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                "mrp": "399.00",
                "price": "249.00",
                "stock": 70,
                "short": "Quick-read thermometer for home temperature checks.",
                "description": "Digital clinical thermometer for routine fever monitoring.",
                "manufacturer": "LifeTrack Devices",
                "image": "Laboratory thermometer-03.jpg",
                "specs": {"Reading Type": "Digital", "Use": "Oral/Axillary", "Warranty": "6 Months"},
            },
            {
                "name": "Basic Surgical Instrument Kit",
                "sku": "MM-SK-001",
                "category": "Surgical Instruments",
                "brand": "SterilePro",
                "type": Product.ProductType.SURGICAL_EQUIPMENT,
                "mrp": "4999.00",
                "price": "4299.00",
                "stock": 12,
                "short": "Reusable stainless-steel surgical instrument kit.",
                "description": "Basic surgical kit with scissors, forceps, needle holder, and tray for clinical workflows.",
                "manufacturer": "SterilePro Supplies",
                "image": "Surgical instrument arranged in a theatre.jpg",
                "specs": {"Material": "Stainless steel", "Sterilizable": "Yes", "Included": "Scissors, forceps, needle holder"},
            },
            {
                "name": "Portable First Aid Kit",
                "sku": "MM-FA-001",
                "category": "First Aid",
                "brand": "HealthPlus",
                "type": Product.ProductType.FIRST_AID,
                "mrp": "899.00",
                "price": "649.00",
                "stock": 40,
                "short": "Emergency first-aid kit for home and travel.",
                "description": "Compact first-aid kit with essential wound-care and emergency supplies.",
                "manufacturer": "HealthPlus Care",
                "image": "First aid kit.jpg",
                "specs": {"Use": "Home, clinic, travel", "Case": "Portable", "Items": "Bandages, gauze, tape"},
            },
            {
                "name": "Manual Wheelchair",
                "sku": "MM-WC-001",
                "category": "Mobility Support",
                "brand": "CareMate",
                "type": Product.ProductType.ORTHOPEDIC_PRODUCT,
                "mrp": "8999.00",
                "price": "7499.00",
                "stock": 8,
                "short": "Foldable manual wheelchair for mobility support.",
                "description": "Manual wheelchair for patient mobility in home-care and clinic settings.",
                "manufacturer": "CareMate Mobility",
                "image": "Hand-operated wheelchair (38791720670).jpg",
                "specs": {"Frame": "Foldable", "Load Capacity": "100 kg", "Warranty": "1 Year"},
            },
            {
                "name": "Paracetamol 500 mg Tablets",
                "sku": "MM-MED-001",
                "category": "Pain Relief",
                "brand": "HealthPlus",
                "type": Product.ProductType.MEDICINE,
                "mrp": "45.00",
                "price": "30.00",
                "stock": 120,
                "short": "Common fever and pain relief medicine.",
                "description": "Paracetamol tablets for fever and mild pain relief. Use as directed by a healthcare professional.",
                "manufacturer": "HealthPlus Pharma",
                "composition": "Paracetamol 500 mg",
                "pack_size": "Strip of 15 tablets",
                "image": "Tylenol 8 hour pills closeup.jpg",
            },
            {
                "name": "Amoxicillin 500 mg Capsules",
                "sku": "MM-RX-001",
                "category": "Antibiotics",
                "brand": "HealthPlus",
                "type": Product.ProductType.MEDICINE,
                "mrp": "180.00",
                "price": "145.00",
                "stock": 60,
                "requires_prescription": True,
                "short": "Prescription-required antibiotic medicine.",
                "description": "Amoxicillin capsules should be purchased only with a valid prescription and professional guidance.",
                "manufacturer": "HealthPlus Pharma",
                "composition": "Amoxicillin 500 mg",
                "pack_size": "Strip of 10 capsules",
                "image": "Tylenol 8 hour pills closeup.jpg",
            },
        ]

        products = {}
        for spec in product_specs:
            product = Product.objects.create(
                name=spec["name"],
                slug=slugify(spec["name"]),
                sku=spec["sku"],
                category=self.categories[spec["category"]],
                brand=self.brands[spec["brand"]],
                product_type=spec["type"],
                short_description=spec["short"],
                description=spec["description"],
                mrp=Decimal(spec["mrp"]),
                selling_price=Decimal(spec["price"]),
                stock_quantity=spec["stock"],
                requires_prescription=spec.get("requires_prescription", False),
                requires_business_license=spec["type"] in {
                    Product.ProductType.MEDICINE,
                    Product.ProductType.MEDICAL_EQUIPMENT,
                    Product.ProductType.SURGICAL_EQUIPMENT,
                    Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                    Product.ProductType.LAB_EQUIPMENT,
                },
                required_license_type=(
                    Product.RegulationType.DRUG_SALE
                    if spec["type"] == Product.ProductType.MEDICINE
                    else Product.RegulationType.MEDICAL_DEVICE_SALE
                    if spec["type"]
                    in {
                        Product.ProductType.MEDICAL_EQUIPMENT,
                        Product.ProductType.SURGICAL_EQUIPMENT,
                        Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                        Product.ProductType.LAB_EQUIPMENT,
                    }
                    else Product.RegulationType.NONE
                ),
                manufacturer=spec.get("manufacturer", ""),
                composition=spec.get("composition", ""),
                pack_size=spec.get("pack_size", ""),
                is_active=True,
                is_featured=True,
                seo_title=f"{spec['name']} | MediMart",
                seo_description=spec["short"],
            )
            if spec.get("image"):
                self.attach_commons_image(product, "image", spec["image"], f"{product.slug}.jpg")
            for name, value in spec.get("specs", {}).items():
                ProductSpecification.objects.create(product=product, name=name, value=value)
            if product.image:
                ProductImage.objects.create(
                    product=product,
                    image=product.image,
                    alt_text=product.name,
                    is_primary=True,
                )
            products[spec["sku"]] = product
        return products

    def create_vendors_and_offers(self):
        vendor = Vendor.objects.create(
            user=self.users["vendor"],
            business_name="MediMart Verified Devices",
            owner_name="Riya Kapoor",
            email="vendor@gmail.com",
            phone="9876543210",
            address="24 Health Market Road, Bengaluru, Karnataka",
            gst_number="29ABCDE1234F1Z5",
            license_number="DEV-LIC-2026",
            business_type=Vendor.BusinessType.MEDICAL_EQUIPMENT,
            bank_name="Demo Bank",
            bank_account_number="1234567890",
            ifsc_code="DEMO0001234",
            is_approved=True,
            is_active=True,
        )
        pharmacy = Vendor.objects.create(
            user=self.users["pharmacy"],
            business_name="CityCare Pharmacy",
            owner_name="Kiran Patel",
            email="pharmacy@gmail.com",
            phone="9876501234",
            address="12 Clinic Lane, Pune, Maharashtra",
            gst_number="27ABCDE1234F1Z2",
            license_number="PHARM-LIC-2026",
            business_type=Vendor.BusinessType.PHARMACY,
            bank_name="Demo Bank",
            bank_account_number="2234567890",
            ifsc_code="DEMO0002234",
            is_approved=True,
            is_active=True,
        )
        manufacturer = Vendor.objects.create(
            user=self.users["manufacturer"],
            business_name="PulseCare Manufacturing",
            owner_name="Dev Iyer",
            email="manufacturer@gmail.com",
            phone="9876512340",
            address="88 Biomedical Park, Hyderabad, Telangana",
            gst_number="36ABCDE1234F1Z7",
            license_number="MFG-LIC-2026",
            business_type=Vendor.BusinessType.MANUFACTURER,
            bank_name="Demo Bank",
            bank_account_number="3234567890",
            ifsc_code="DEMO0003234",
            is_approved=True,
            is_active=True,
        )
        vendor_license = BusinessLicense.objects.create(
            vendor=vendor,
            license_type=BusinessLicense.LicenseType.DEVICE_SALE,
            license_number=vendor.license_number,
            form_number="MD-42",
            legal_name=vendor.business_name,
            premises_address=vendor.address,
            state="Karnataka",
            licensing_authority="State Licensing Authority",
            status=BusinessLicense.Status.VERIFIED,
            verification_source=BusinessLicense.VerificationSource.ONDLS,
            reviewed_by=self.users["admin"],
            reviewed_at=timezone.now(),
            issued_on=timezone.localdate() - timedelta(days=90),
            valid_until=timezone.localdate() + timedelta(days=365),
        )
        vendor_license.document.save("device-sale-licence.pdf", ContentFile(b"%PDF-1.4\n% Demo licence\n%%EOF"), save=True)
        pharmacy_license = BusinessLicense.objects.create(
            vendor=pharmacy,
            license_type=BusinessLicense.LicenseType.DRUG_RETAIL,
            license_number=pharmacy.license_number,
            form_number="Form 20 / 21",
            legal_name=pharmacy.business_name,
            premises_address=pharmacy.address,
            state="Maharashtra",
            licensing_authority="State Drugs Control Administration",
            status=BusinessLicense.Status.VERIFIED,
            verification_source=BusinessLicense.VerificationSource.ONDLS,
            reviewed_by=self.users["admin"],
            reviewed_at=timezone.now(),
            issued_on=timezone.localdate() - timedelta(days=90),
            valid_until=timezone.localdate() + timedelta(days=365),
        )
        pharmacy_license.document.save("drug-retail-licence.pdf", ContentFile(b"%PDF-1.4\n% Demo licence\n%%EOF"), save=True)
        manufacturer_license = BusinessLicense.objects.create(
            vendor=manufacturer,
            license_type=BusinessLicense.LicenseType.DEVICE_MANUFACTURING,
            license_number=manufacturer.license_number,
            form_number="MD-5",
            legal_name=manufacturer.business_name,
            premises_address=manufacturer.address,
            state="Telangana",
            licensing_authority="State Licensing Authority",
            status=BusinessLicense.Status.VERIFIED,
            verification_source=BusinessLicense.VerificationSource.CDSCO_MD,
            reviewed_by=self.users["admin"],
            reviewed_at=timezone.now(),
            issued_on=timezone.localdate() - timedelta(days=90),
            valid_until=timezone.localdate() + timedelta(days=365),
        )
        manufacturer_license.document.save("device-manufacturing-licence.pdf", ContentFile(b"%PDF-1.4\n% Demo licence\n%%EOF"), save=True)
        BusinessLicense.objects.create(
            vendor=manufacturer,
            license_type=BusinessLicense.LicenseType.DEVICE_IMPORT,
            license_number="MD-15-DEMO-REVIEW",
            form_number="MD-15",
            legal_name=manufacturer.business_name,
            premises_address=manufacturer.address,
            state="Telangana",
            licensing_authority="Central Licensing Authority",
            status=BusinessLicense.Status.MANUAL_REVIEW,
            verification_source=BusinessLicense.VerificationSource.APPLICANT,
            review_notes="Demo expansion application awaiting registry and evidence review.",
        )
        vendors = {"vendor": vendor, "pharmacy": pharmacy, "manufacturer": manufacturer}

        for index, product in enumerate(self.products.values(), start=1):
            equipment_types = {
                Product.ProductType.MEDICAL_EQUIPMENT,
                Product.ProductType.SURGICAL_EQUIPMENT,
                Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                Product.ProductType.LAB_EQUIPMENT,
                Product.ProductType.FITNESS_EQUIPMENT,
            }
            if product.product_type == Product.ProductType.MEDICINE:
                primary_vendor = pharmacy
            elif product.product_type in equipment_types:
                primary_vendor = manufacturer
            else:
                primary_vendor = vendor
            secondary_vendor = vendor if primary_vendor == pharmacy else pharmacy
            VendorProduct.objects.create(
                vendor=primary_vendor,
                product=product,
                price=product.selling_price,
                stock_quantity=max(product.stock_quantity // 2, 5),
                delivery_time="1-2 days",
                warranty="1 Year" if product.product_type != Product.ProductType.MEDICINE else "",
                offer_text="Fast verified MediMart seller",
                seller_rating=Decimal("4.60"),
                is_active=True,
                is_approved=True,
            )
            VendorProduct.objects.create(
                vendor=secondary_vendor,
                product=product,
                price=product.selling_price + Decimal(index * 25),
                stock_quantity=max(product.stock_quantity // 3, 4),
                delivery_time="2-4 days",
                warranty="6 Months" if product.product_type != Product.ProductType.MEDICINE else "",
                offer_text="Value seller offer",
                seller_rating=Decimal("4.30"),
                is_active=True,
                is_approved=True,
            )
        return vendors

    def create_customer_data(self):
        customer = self.users["customer"]
        address = Address.objects.create(
            user=customer,
            full_name="Aarav Sharma",
            phone="9999999999",
            address_line_1="Flat 402, Green Residency",
            address_line_2="Near City Hospital",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
            landmark="Opposite metro station",
            address_type=Address.AddressType.HOME,
            is_default=True,
        )
        work_address = Address.objects.create(
            user=customer,
            full_name="Aarav Sharma",
            phone="9999999999",
            address_line_1="MediMart Demo Office",
            city="Bengaluru",
            state="Karnataka",
            pincode="560002",
            address_type=Address.AddressType.WORK,
        )

        today = timezone.localdate()
        coupon = Coupon.objects.create(
            code="MEDI10",
            discount_type=Coupon.DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            minimum_order=Decimal("500.00"),
            maximum_discount=Decimal("250.00"),
            start_date=today,
            end_date=today + timedelta(days=90),
            usage_limit=100,
            is_active=True,
        )
        Coupon.objects.create(
            code="CARE100",
            discount_type=Coupon.DiscountType.FIXED,
            discount_value=Decimal("100.00"),
            minimum_order=Decimal("1000.00"),
            maximum_discount=Decimal("100.00"),
            start_date=today,
            end_date=today + timedelta(days=90),
            usage_limit=100,
            is_active=True,
        )

        prescription = Prescription.objects.create(
            user=customer,
            doctor_name="Dr Ananya Mehta",
            prescription_date=today,
            doctor_registration_number="KMC-DEMO-1024",
            valid_until=today + timedelta(days=90),
            max_fulfillments=3,
            notes="Demo approved prescription for prescription-required medicines.",
            status=Prescription.Status.APPROVED,
            reviewed_by=self.users["admin"],
            reviewed_at=timezone.now(),
        )
        prescription.file.save(
            "demo-prescription.pdf",
            ContentFile(b"%PDF-1.4\n% MediMart demo prescription placeholder\n%%EOF"),
            save=True,
        )
        rx_product = self.products["MM-RX-001"]
        PrescriptionItem.objects.create(
            prescription=prescription,
            product=rx_product,
            prescribed_name=rx_product.name,
            dosage="As directed by the prescribing doctor",
            quantity=6,
        )

        bp_offer = self.products["MM-BP-001"].vendor_products.first()
        rx_offer = self.products["MM-RX-001"].vendor_products.first()
        order = Order.objects.create(
            customer=customer,
            address=address,
            address_snapshot=self.address_snapshot(address),
            subtotal=bp_offer.price + rx_offer.price,
            discount=Decimal("100.00"),
            delivery_charge=Decimal("49.00"),
            total_amount=bp_offer.price + rx_offer.price - Decimal("100.00") + Decimal("49.00"),
            coupon=coupon,
            payment_method=Order.PaymentMethod.RAZORPAY,
            payment_status=Order.PaymentStatus.PAID,
            order_status=Order.OrderStatus.OUT_FOR_DELIVERY,
            delivery_staff=self.users["delivery"],
        )
        for offer in [bp_offer, rx_offer]:
            item = OrderItem.objects.create(
                order=order,
                vendor_product=offer,
                vendor=offer.vendor,
                product=offer.product,
                product_name=offer.product.name,
                seller_name=offer.vendor.business_name,
                sku=offer.product.sku,
                quantity=1,
                unit_price=offer.price,
                total_price=offer.price,
            )
            if offer.product.sku == "MM-BP-001":
                Review.objects.create(
                    user=customer,
                    product=offer.product,
                    order_item=item,
                    rating=5,
                    title="Very easy to use",
                    comment="The monitor is simple, clear, and useful for home readings.",
                    is_approved=True,
                )
        for status, note in [
            (Order.OrderStatus.CONFIRMED, "Order confirmed."),
            (Order.OrderStatus.PACKED, "Packed by seller."),
            (Order.OrderStatus.SHIPPED, "Handed to delivery team."),
            (Order.OrderStatus.OUT_FOR_DELIVERY, "Out for delivery."),
        ]:
            OrderStatusHistory.objects.create(order=order, status=status, note=note)
        Payment.objects.create(
            order=order,
            payment_method=order.payment_method,
            amount=order.total_amount,
            status=order.payment_status,
            transaction_id=f"RAZORPAY-DEMO-{order.order_number}",
        )

        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.create(cart=cart, vendor_product=self.products["MM-PO-001"].vendor_products.first(), quantity=1)
        wishlist, _ = Wishlist.objects.get_or_create(user=customer)
        WishlistItem.objects.create(wishlist=wishlist, product=self.products["MM-GL-001"])
        WishlistItem.objects.create(wishlist=wishlist, product=self.products["MM-WC-001"])

        return {"address": address, "work_address": work_address, "order": order}

    def create_doctors(self):
        DoctorProfile.objects.create(
            user=self.users["doctor"],
            full_name="Dr Ananya Mehta",
            specialization="General Medicine",
            experience_years=9,
            clinic_name="MediMart Care Clinic",
            clinic_address="18 Wellness Avenue, Bengaluru, Karnataka",
            phone="9988776655",
            consultation_fee=Decimal("600.00"),
            availability="Mon-Fri, 10 AM to 5 PM",
            is_verified=True,
        )

    def create_blog(self):
        category = BlogCategory.objects.create(
            name="Health Guides",
            slug="health-guides",
            description="Simple educational articles for everyday healthcare.",
        )
        articles = [
            {
                "title": "How to Monitor Blood Pressure at Home",
                "slug": "how-to-monitor-blood-pressure-at-home",
                "excerpt": "Simple tips for routine BP tracking with a digital monitor.",
                "content": "Prepare before you measure. Avoid exercise, caffeine, smoking, and a heavy meal for at least 30 minutes when possible. Empty your bladder, sit quietly for five minutes, and place both feet flat on the floor.\n\nUse a validated upper-arm monitor with a cuff that fits your arm. Put the cuff on bare skin, keep your back supported, and rest your arm so the cuff is close to heart level. Stay still and avoid talking while the machine is measuring.\n\nTake two readings about one minute apart and record both results with the date and time. Measuring at a similar time each day makes the log easier for a clinician to interpret. Do not change prescribed treatment based only on a home reading.\n\nSeek professional advice if readings are repeatedly outside the range your clinician gave you. Very high readings accompanied by chest pain, severe headache, weakness, confusion, breathing difficulty, or vision changes require urgent medical assessment.",
                "image": "Digital Blood Pressure Monitor.jpg",
            },
            {
                "title": "Using a Pulse Oximeter Safely",
                "slug": "using-a-pulse-oximeter-safely",
                "excerpt": "What to remember when checking oxygen saturation.",
                "content": "A pulse oximeter estimates oxygen saturation and pulse rate, but the number should always be considered together with symptoms and medical history. Cold hands, movement, nail polish, artificial nails, poor circulation, and a loosely fitted device can affect the reading.\n\nRest for a few minutes before measuring. Warm the hand, remove nail polish when practical, and place the device fully on a fingertip. Keep the hand relaxed and still at about chest level while you wait for a stable number. Try another finger if the signal does not settle.\n\nRecord the value, pulse rate, time, and any symptoms. Trends are generally more useful than repeatedly checking within a few seconds. Consumer devices may be less accurate at lower oxygen levels and should not be used to delay medical care.\n\nFollow the action range provided by your clinician. Seek prompt medical advice for persistent unexpected readings or worsening symptoms, and seek emergency help for severe breathing difficulty, bluish lips, confusion, fainting, or chest pain.",
                "image": "FingertipPulseOximeterMD300C2.jpg",
            },
            {
                "title": "What to Keep in a First Aid Kit",
                "slug": "what-to-keep-in-a-first-aid-kit",
                "excerpt": "Basic first-aid supplies for home and travel.",
                "content": "A home first aid kit should help with common minor injuries while making it easy to recognize when professional care is needed. Store supplies together in a clean, dry, clearly marked container that adults can reach quickly but children cannot access unsupervised.\n\nUseful basics include adhesive bandages in several sizes, sterile gauze pads, roller bandages, medical tape, antiseptic wipes, disposable gloves, blunt-tip scissors, tweezers, a digital thermometer, and a simple cold pack. Add personal items recommended by your clinician and emergency contact information for household members.\n\nCheck the kit every few months. Replace opened, damaged, wet, or expired products and make sure batteries still work. Keep a smaller kit in the car or travel bag, accounting for temperature-sensitive products and airline restrictions.\n\nA first aid kit is for immediate support, not a substitute for medical treatment. Heavy bleeding, breathing problems, suspected fractures, significant burns, poisoning, loss of consciousness, severe allergic reactions, or rapidly worsening symptoms need urgent professional help.",
                "image": "First aid kit.jpg",
            },
        ]
        for article in articles:
            post = BlogPost.objects.create(
                title=article["title"],
                slug=article["slug"],
                category=category,
                author=self.users["admin"],
                excerpt=article["excerpt"],
                content=article["content"],
                status=BlogPost.Status.PUBLISHED,
                published_at=timezone.now(),
            )
            self.attach_commons_image(post, "image", article["image"], f"{post.slug}.jpg")

    def create_support_and_notifications(self):
        ticket = SupportTicket.objects.create(
            user=self.users["customer"],
            subject="Need help with delivery time",
            category=SupportTicket.Category.ORDER,
            message="Please confirm when my order will arrive.",
            order_number=Order.objects.filter(customer=self.users["customer"]).first().order_number,
            status=SupportTicket.Status.IN_PROGRESS,
        )
        SupportMessage.objects.create(
            ticket=ticket,
            sender=self.users["support"],
            message="Your order is currently out for delivery and should arrive today.",
            is_staff_reply=True,
        )
        Notification.objects.create(
            user=self.users["customer"],
            title="Order out for delivery",
            message="Your MediMart order is out for delivery.",
            notification_type=Notification.NotificationType.ORDER,
        )
        Notification.objects.create(
            user=self.users["customer"],
            title="Prescription approved",
            message="Your uploaded prescription has been approved.",
            notification_type=Notification.NotificationType.PRESCRIPTION,
            is_read=True,
        )
        Notification.objects.create(
            user=self.users["vendor"],
            title="Vendor offer approved",
            message="Your seller offers are approved and visible to customers.",
            notification_type=Notification.NotificationType.OFFER,
        )

    def attach_commons_image(self, instance, field_name, commons_filename, local_filename):
        source_url = self.commons_file_url(commons_filename)
        try:
            content = self.download_url(source_url)
        except URLError as error:
            self.stderr.write(f"Could not download {commons_filename}: {error}")
            local_fallback = self.local_catalog_fallback(instance)
            if local_fallback and local_fallback.exists():
                fallback_name = f"{slugify(getattr(instance, 'name', local_filename))}.webp"
                getattr(instance, field_name).save(
                    fallback_name,
                    ContentFile(local_fallback.read_bytes()),
                    save=True,
                )
                return
            label = getattr(instance, "name", None) or getattr(instance, "title", None) or Path(local_filename).stem
            fallback_url = self.placeholder_url(label)
            try:
                content = self.download_url(fallback_url)
            except URLError as fallback_error:
                self.stderr.write(f"Could not download fallback image for {label}: {fallback_error}")
                return
            local_filename = Path(local_filename).with_suffix(".png").name
        getattr(instance, field_name).save(local_filename, ContentFile(content), save=True)

    def local_catalog_fallback(self, instance):
        if isinstance(instance, BlogPost):
            image_by_slug = {
                "how-to-monitor-blood-pressure-at-home": "blood-pressure-home.webp",
                "using-a-pulse-oximeter-safely": "pulse-oximeter-home.webp",
                "what-to-keep-in-a-first-aid-kit": "first-aid-kit-home.webp",
            }
            filename = image_by_slug.get(instance.slug)
            if filename:
                return Path(__file__).resolve().parents[3] / "static" / "images" / "blog" / filename
            return None
        if not isinstance(instance, Product):
            return None
        image_by_type = {
            Product.ProductType.MEDICINE: "medicines.webp",
            Product.ProductType.MEDICAL_EQUIPMENT: "medical-equipment.webp",
            Product.ProductType.DIAGNOSTIC_EQUIPMENT: "diagnostic-equipment.webp",
            Product.ProductType.SURGICAL_EQUIPMENT: "surgical-equipment.webp",
            Product.ProductType.FIRST_AID: "healthcare-products.webp",
            Product.ProductType.ORTHOPEDIC_PRODUCT: "medical-equipment.webp",
        }
        filename = image_by_type.get(instance.product_type, "healthcare-products.webp")
        return Path("media") / "categories" / filename

    def commons_file_url(self, filename):
        return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}"

    def placeholder_url(self, label):
        return f"https://placehold.co/900x650/png?text={quote(label[:80])}"

    def download_url(self, url):
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MediMartDemoSeeder/1.0)",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urlopen(request, timeout=30) as response:
            return response.read()

    def address_snapshot(self, address):
        return "\n".join(
            part
            for part in [
                address.full_name,
                address.phone,
                address.address_line_1,
                address.address_line_2,
                f"{address.city}, {address.state} - {address.pincode}",
                f"Landmark: {address.landmark}" if address.landmark else "",
            ]
            if part
        )

    def write_credentials_file(self):
        image_sources = [
            "Digital Blood Pressure Monitor.jpg",
            "FingertipPulseOximeterMD300C2.jpg",
            "Glucometer002.jpg",
            "Nebulizer.JPG",
            "Laboratory thermometer-03.jpg",
            "Surgical instrument arranged in a theatre.jpg",
            "First aid kit.jpg",
            "Hand-operated wheelchair (38791720670).jpg",
            "Tylenol 8 hour pills closeup.jpg",
        ]
        lines = [
            "# MediMart Demo Credentials",
            "",
            "Generated by `python manage.py reset_demo_data`.",
            "",
            "All demo users use the same password:",
            "",
            f"`{DEMO_PASSWORD}`",
            "",
            "| User Type | Username | Email | Password | Notes |",
            "| --- | --- | --- | --- | --- |",
            "| Admin | `admin` | `admin@gmail.com` | `MediMart@2026` | Complete custom Operations Center access |",
            "| Customer | `customer` | `customer@gmail.com` | `MediMart@2026` | Has address, cart, saved items, prescription, assigned delivery order, review, support ticket |",
            "| Vendor | `vendor` | `vendor@gmail.com` | `MediMart@2026` | Approved medical equipment seller |",
            "| Manufacturer | `manufacturer` | `manufacturer@gmail.com` | `MediMart@2026` | Approved equipment manufacturer with product offers |",
            "| Pharmacy | `pharmacy` | `pharmacy@gmail.com` | `MediMart@2026` | Approved pharmacy seller |",
            "| Doctor | `doctor` | `doctor@gmail.com` | `MediMart@2026` | Verified doctor dashboard/profile |",
            "| Delivery Staff | `delivery` | `delivery@gmail.com` | `MediMart@2026` | Delivery dashboard access |",
            "| Support Staff | `support` | `support@gmail.com` | `MediMart@2026` | Staff account for support replies |",
            "| Compliance Officer | `compliance` | `compliance@gmail.com` | `MediMart@2026` | Seller and business licence review |",
            "| Catalog Manager | `catalog` | `catalog@gmail.com` | `MediMart@2026` | Product and seller-offer approval |",
            "| Operations Manager | `operations` | `operations@gmail.com` | `MediMart@2026` | Cross-functional operations access |",
            "| Warehouse Manager | `warehouse` | `warehouse@gmail.com` | `MediMart@2026` | Inventory and fulfillment management |",
            "",
            "## Useful Demo URLs",
            "",
            "- Home: `http://127.0.0.1:8000/`",
            "- Products: `http://127.0.0.1:8000/products/`",
            "- Operations Center: `http://127.0.0.1:8000/admin-dashboard/`",
            "- Admin Dashboard: `http://127.0.0.1:8000/admin-dashboard/`",
            "- Delivery Dashboard: `http://127.0.0.1:8000/delivery-dashboard/`",
            "- Doctor Dashboard: `http://127.0.0.1:8000/doctor-dashboard/`",
            "- Vendor Dashboard: `http://127.0.0.1:8000/vendor-dashboard/`",
            "- Blog: `http://127.0.0.1:8000/blog/`",
            "",
            "## Seeded Demo Data",
            "",
            "- Categories: medicines, medical equipment, diagnostic equipment, surgical equipment, healthcare products.",
            "- Products: BP monitor, pulse oximeter, glucometer, nebulizer, thermometer, surgical kit, first aid kit, wheelchair, paracetamol, amoxicillin.",
            "- Vendors: one medical equipment seller, one equipment manufacturer, and one pharmacy with approved offers, verified licences, and one pending MD-15 review.",
            "- Customer data: addresses, cart, saved items, approved prescription, paid order, assigned delivery, review, notifications, support ticket.",
            "- Extras: verified doctor profile and published blog articles.",
            "",
            "## Online Image Sources",
            "",
            "Images are downloaded from Wikimedia Commons through `Special:FilePath` using these source file names:",
            "",
        ]
        lines.extend(f"- `{name}`" for name in image_sources)
        lines.extend(
            [
                "",
                "If Wikimedia blocks a product-image download, the seeder first uses MediMart's curated local catalog photography. A labeled online placeholder is used only when no matching local asset is available.",
                "",
                "Review each Wikimedia Commons file page for exact license and attribution requirements before using the demo images outside local testing.",
                "",
            ]
        )
        Path("DEMO_CREDENTIALS.md").write_text("\n".join(lines), encoding="utf-8")
