from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from products.models import Product
from vendors.models import BusinessLicense, Vendor, VendorProduct


class Command(BaseCommand):
    help = "Create approved demo vendors and seller offers for MediMart."

    def handle(self, *args, **options):
        call_command("seed_products")

        User = get_user_model()
        vendor_data = [
            {
                "username": "medimart_vendor_healthplus",
                "business_name": "HealthPlus Pharmacy",
                "owner_name": "HealthPlus Owner",
                "email": "vendor.healthplus@gmail.com",
                "phone": "9000000001",
                "business_type": Vendor.BusinessType.PHARMACY,
                "license_number": "HP-LIC-1001",
                "address": "12 Wellness Street, Pune, Maharashtra",
            },
            {
                "username": "medimart_vendor_caremate",
                "business_name": "CareMate Medical Supplies",
                "owner_name": "CareMate Owner",
                "email": "vendor.caremate@gmail.com",
                "phone": "9000000002",
                "business_type": Vendor.BusinessType.MEDICAL_EQUIPMENT,
                "license_number": "CM-LIC-1002",
                "address": "45 Clinic Road, Mumbai, Maharashtra",
            },
            {
                "username": "medimart_vendor_sterilepro",
                "business_name": "SterilePro Surgical Store",
                "owner_name": "SterilePro Owner",
                "email": "vendor.sterilepro@gmail.com",
                "phone": "9000000003",
                "business_type": Vendor.BusinessType.SURGICAL_EQUIPMENT,
                "license_number": "SP-LIC-1003",
                "address": "88 Hospital Avenue, Bengaluru, Karnataka",
            },
        ]

        vendors = {}
        for item in vendor_data:
            user, created = User.objects.get_or_create(
                username=item["username"],
                defaults={
                    "email": item["email"],
                    "first_name": item["owner_name"].split()[0],
                    "last_name": "Vendor",
                },
            )
            if created:
                user.set_password("MediMart@12345")
                user.save()

            vendor, _ = Vendor.objects.update_or_create(
                user=user,
                defaults={
                    "business_name": item["business_name"],
                    "owner_name": item["owner_name"],
                    "email": item["email"],
                    "phone": item["phone"],
                    "address": item["address"],
                    "license_number": item["license_number"],
                    "business_type": item["business_type"],
                    "gst_number": "GST-DEMO",
                    "is_approved": True,
                    "is_active": True,
                },
            )
            vendors[item["business_name"]] = vendor
            license_type = (
                BusinessLicense.LicenseType.DRUG_RETAIL
                if item["business_type"] == Vendor.BusinessType.PHARMACY
                else BusinessLicense.LicenseType.DEVICE_SALE
            )
            BusinessLicense.objects.update_or_create(
                vendor=vendor,
                license_type=license_type,
                license_number=item["license_number"],
                defaults={
                    "legal_name": item["business_name"],
                    "premises_address": item["address"],
                    "status": BusinessLicense.Status.VERIFIED,
                    "verification_source": BusinessLicense.VerificationSource.ONDLS,
                },
            )

        offers = [
            ("HealthPlus Pharmacy", "MM-MED-001", Decimal("24.00"), 80, "Same day", ""),
            ("HealthPlus Pharmacy", "MM-RX-001", Decimal("145.00"), 40, "Same day", ""),
            ("CareMate Medical Supplies", "MM-BP-001", Decimal("1799.00"), 18, "2 days", "1 Year"),
            ("HealthPlus Pharmacy", "MM-BP-001", Decimal("1849.00"), 12, "1 day", "1 Year"),
            ("CareMate Medical Supplies", "MM-PO-001", Decimal("899.00"), 30, "2 days", "6 Months"),
            ("HealthPlus Pharmacy", "MM-PO-001", Decimal("949.00"), 22, "Same day", "6 Months"),
            ("SterilePro Surgical Store", "MM-SG-001", Decimal("499.00"), 100, "2-3 days", ""),
            ("SterilePro Surgical Store", "MM-SK-001", Decimal("4299.00"), 12, "3 days", ""),
            ("CareMate Medical Supplies", "MM-PM-001", Decimal("57999.00"), 4, "5-7 days", "2 Years"),
            ("CareMate Medical Supplies", "MM-HB-001", Decimal("28499.00"), 5, "4-6 days", "1 Year"),
            ("CareMate Medical Supplies", "MM-CF-001", Decimal("18999.00"), 6, "3-5 days", "1 Year"),
        ]

        for business_name, sku, price, stock, delivery_time, warranty in offers:
            product = Product.objects.get(sku=sku)
            VendorProduct.objects.update_or_create(
                vendor=vendors[business_name],
                product=product,
                defaults={
                    "price": price,
                    "stock_quantity": stock,
                    "delivery_time": delivery_time,
                    "warranty": warranty,
                    "seller_rating": Decimal("4.60"),
                    "offer_text": "Demo approved seller offer",
                    "is_active": True,
                    "is_approved": True,
                },
            )

        self.stdout.write(self.style.SUCCESS("MediMart demo vendors and offers created."))
