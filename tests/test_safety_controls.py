from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import UserProfile
from orders.models import InventoryBatch, Warehouse
from prescriptions.models import Prescription, PrescriptionItem
from products.models import Brand, Category, Product
from vendors.models import Vendor, VendorProduct


User = get_user_model()


class SafetyControlTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="safety_customer", password="Testpass123!")
        UserProfile.objects.create(user=self.user, role=UserProfile.Role.CUSTOMER)
        self.category = Category.objects.create(name="Safety category", slug="safety-category")
        self.brand = Brand.objects.create(name="Safety brand", slug="safety-brand")

    def test_state_restrictions_support_allow_and_block_lists(self):
        product = Product.objects.create(
            name="State controlled medicine",
            sku="STATE-001",
            category=self.category,
            brand=self.brand,
            product_type=Product.ProductType.MEDICINE,
            description="Safety test product",
            mrp=100,
            selling_price=90,
            state_restrictions={"allowed_states": ["Gujarat"]},
        )

        self.assertTrue(product.is_allowed_in_state("gujarat"))
        self.assertFalse(product.is_allowed_in_state("Maharashtra"))

        product.state_restrictions = ["Rajasthan"]
        self.assertFalse(product.is_allowed_in_state("rajasthan"))
        self.assertTrue(product.is_allowed_in_state("Gujarat"))

    def test_prescription_validation_flags_missing_clinical_evidence(self):
        prescription = Prescription(
            user=self.user,
            patient_name="Patient",
            doctor_name="Doctor",
            prescription_date=date.today(),
            requested_medicines="Medicine",
        )

        flags = prescription.compute_validation_flags(items=[])

        self.assertIn("doctor_registration_missing", flags)
        self.assertIn("prescriber_not_verified", flags)
        self.assertIn("patient_identity_not_verified", flags)

    def test_inventory_batch_rejects_invalid_temperature_and_expiry_ranges(self):
        vendor_user = User.objects.create_user(username="safety_vendor", password="Testpass123!")
        UserProfile.objects.create(user=vendor_user, role=UserProfile.Role.VENDOR)
        vendor = Vendor.objects.create(
            user=vendor_user,
            business_name="Safety vendor",
            owner_name="Safety Owner",
            email="safety.vendor@gmail.com",
            phone="9876543210",
            address="Safety address",
            license_number="SAFE-LIC-001",
            business_type=Vendor.BusinessType.PHARMACY,
            is_approved=True,
        )
        offer = VendorProduct.objects.create(
            vendor=vendor,
            product=Product.objects.create(
                name="Cold chain product",
                sku="COLD-001",
                category=self.category,
                brand=self.brand,
                product_type=Product.ProductType.MEDICINE,
                description="Cold chain test product",
                mrp=100,
                selling_price=90,
            ),
            price=90,
            stock_quantity=10,
            is_approved=True,
            is_active=True,
        )
        warehouse = Warehouse.objects.create(
            code="SAFE-WH",
            name="Safety warehouse",
            address="Warehouse address",
            pincode="380001",
        )
        batch = InventoryBatch(
            vendor_product=offer,
            warehouse=warehouse,
            batch_number="SAFE-BATCH",
            manufactured_on=date(2026, 1, 1),
            expires_on=date(2025, 12, 31),
            storage_min_celsius=8,
            storage_max_celsius=2,
        )

        with self.assertRaises(ValidationError) as error:
            batch.full_clean()

        self.assertIn("storage_max_celsius", error.exception.message_dict)
        self.assertIn("expires_on", error.exception.message_dict)
