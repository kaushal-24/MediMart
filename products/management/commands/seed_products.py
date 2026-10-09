from decimal import Decimal

from django.core.management.base import BaseCommand

from products.models import Brand, Category, Product, ProductSpecification


class Command(BaseCommand):
    help = "Create demo categories, brands, and products for MediMart."

    def handle(self, *args, **options):
        categories = {
            "Medicines": [
                "Pain Relief",
                "Cold & Cough",
                "Diabetes",
                "Blood Pressure",
                "Antibiotics",
            ],
            "Medical Equipment": [
                "Blood Pressure Monitors",
                "Glucometers",
                "Pulse Oximeters",
                "Nebulizers",
                "Patient Monitors",
                "Hospital Beds",
            ],
            "Surgical Equipment": [
                "Surgical Instruments",
                "Dressing Equipment",
                "PPE",
                "Surgical Kits",
            ],
            "Diagnostic Equipment": [
                "Testing Kits",
                "Lab Equipment",
                "Centrifuges",
            ],
            "Personal Care": [
                "Skin Care",
                "Hygiene",
            ],
        }

        created_categories = {}
        for parent_name, child_names in categories.items():
            parent, _ = Category.objects.get_or_create(name=parent_name)
            created_categories[parent_name] = parent
            for child_name in child_names:
                child, _ = Category.objects.get_or_create(name=child_name, parent=parent)
                created_categories[child_name] = child

        brands = {}
        for brand_name in ["HealthPlus", "CareMate", "MediSure", "LifeTrack", "SterilePro"]:
            brand, _ = Brand.objects.get_or_create(name=brand_name)
            brands[brand_name] = brand

        products = [
            {
                "name": "Digital Blood Pressure Monitor",
                "sku": "MM-BP-001",
                "category": "Blood Pressure Monitors",
                "brand": "LifeTrack",
                "product_type": Product.ProductType.MEDICAL_EQUIPMENT,
                "short_description": "Automatic BP monitor for home blood pressure tracking.",
                "description": "A simple upper-arm digital blood pressure monitor with clear readings and memory support.",
                "mrp": Decimal("2499.00"),
                "selling_price": Decimal("1799.00"),
                "stock_quantity": 18,
                "manufacturer": "LifeTrack Devices",
                "warranty": "1 Year",
                "specifications": {
                    "Display": "Digital LCD",
                    "Power": "4 AA batteries or adapter",
                    "Cuff Size": "22-42 cm",
                },
            },
            {
                "name": "Pulse Oximeter",
                "sku": "MM-PO-001",
                "category": "Pulse Oximeters",
                "brand": "MediSure",
                "product_type": Product.ProductType.MEDICAL_EQUIPMENT,
                "short_description": "Compact fingertip oximeter for SpO2 and pulse readings.",
                "description": "A lightweight pulse oximeter for quick oxygen saturation and pulse checks.",
                "mrp": Decimal("1499.00"),
                "selling_price": Decimal("899.00"),
                "stock_quantity": 30,
                "manufacturer": "MediSure Health",
                "warranty": "6 Months",
                "specifications": {
                    "Display": "OLED",
                    "Measures": "SpO2 and pulse rate",
                    "Power": "2 AAA batteries",
                },
            },
            {
                "name": "Sterile Surgical Gloves",
                "sku": "MM-SG-001",
                "category": "PPE",
                "brand": "SterilePro",
                "product_type": Product.ProductType.SURGICAL_EQUIPMENT,
                "short_description": "Powder-free sterile gloves for clinical use.",
                "description": "Disposable sterile surgical gloves suitable for healthcare and dressing workflows.",
                "mrp": Decimal("650.00"),
                "selling_price": Decimal("499.00"),
                "stock_quantity": 100,
                "manufacturer": "SterilePro Supplies",
                "specifications": {
                    "Material": "Latex",
                    "Sterility": "Sterile",
                    "Pack": "Box of 50 pairs",
                },
            },
            {
                "name": "Glucometer Starter Kit",
                "sku": "MM-GL-001",
                "category": "Glucometers",
                "brand": "CareMate",
                "product_type": Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                "short_description": "Blood sugar monitoring kit with strips and lancets.",
                "description": "A home glucometer kit for regular blood glucose checks.",
                "mrp": Decimal("1299.00"),
                "selling_price": Decimal("999.00"),
                "stock_quantity": 14,
                "manufacturer": "CareMate Diagnostics",
                "warranty": "Lifetime device warranty",
                "specifications": {
                    "Sample Type": "Capillary whole blood",
                    "Result Time": "5 seconds",
                    "Memory": "300 readings",
                },
            },
            {
                "name": "Paracetamol 500 mg Tablets",
                "sku": "MM-MED-001",
                "category": "Pain Relief",
                "brand": "HealthPlus",
                "product_type": Product.ProductType.MEDICINE,
                "short_description": "Common fever and pain relief medicine.",
                "description": "Paracetamol tablets for fever and mild pain relief. Use only as directed by a healthcare professional.",
                "mrp": Decimal("35.00"),
                "selling_price": Decimal("25.00"),
                "stock_quantity": 60,
                "requires_prescription": False,
                "manufacturer": "HealthPlus Pharma",
                "composition": "Paracetamol 500 mg",
                "pack_size": "Strip of 15 tablets",
            },
            {
                "name": "Nebulizer Machine",
                "sku": "MM-NB-001",
                "category": "Nebulizers",
                "brand": "MediSure",
                "product_type": Product.ProductType.MEDICAL_EQUIPMENT,
                "short_description": "Compressor nebulizer for respiratory therapy support.",
                "description": "A compact compressor nebulizer suitable for prescribed respiratory medication delivery.",
                "mrp": Decimal("2399.00"),
                "selling_price": Decimal("1699.00"),
                "stock_quantity": 8,
                "manufacturer": "MediSure Health",
                "warranty": "1 Year",
                "specifications": {
                    "Power": "230V AC",
                    "Medication Capacity": "6 ml",
                    "Flow Rate": "0.2 ml/min",
                },
            },
            {
                "name": "Amoxicillin 500 mg Capsules",
                "sku": "MM-RX-001",
                "category": "Antibiotics",
                "brand": "HealthPlus",
                "product_type": Product.ProductType.MEDICINE,
                "short_description": "Prescription-required antibiotic medicine.",
                "description": "Amoxicillin capsules should be used only with a valid doctor's prescription and professional guidance.",
                "mrp": Decimal("180.00"),
                "selling_price": Decimal("145.00"),
                "stock_quantity": 40,
                "requires_prescription": True,
                "manufacturer": "HealthPlus Pharma",
                "composition": "Amoxicillin 500 mg",
                "pack_size": "Strip of 10 capsules",
            },
            {
                "name": "5-Parameter Patient Monitor",
                "sku": "MM-PM-001",
                "category": "Patient Monitors",
                "brand": "LifeTrack",
                "product_type": Product.ProductType.MEDICAL_EQUIPMENT,
                "short_description": "Multiparameter monitor for clinics and small hospitals.",
                "description": "A professional patient monitor for ECG, SpO2, NIBP, temperature, and respiration monitoring.",
                "mrp": Decimal("64999.00"),
                "selling_price": Decimal("57999.00"),
                "stock_quantity": 4,
                "manufacturer": "LifeTrack Devices",
                "warranty": "2 Years",
                "specifications": {
                    "Parameters": "ECG, SpO2, NIBP, RESP, TEMP",
                    "Display": "12 inch color TFT",
                    "Installation Required": "Yes",
                    "Power": "AC with battery backup",
                },
            },
            {
                "name": "Manual Hospital Bed",
                "sku": "MM-HB-001",
                "category": "Hospital Beds",
                "brand": "CareMate",
                "product_type": Product.ProductType.MEDICAL_EQUIPMENT,
                "short_description": "Two-function manual hospital bed for patient care.",
                "description": "A sturdy manual hospital bed with backrest and knee-rest adjustment for clinics and home care.",
                "mrp": Decimal("32999.00"),
                "selling_price": Decimal("28499.00"),
                "stock_quantity": 5,
                "manufacturer": "CareMate Hospital Furniture",
                "warranty": "1 Year",
                "specifications": {
                    "Material": "Mild steel",
                    "Functions": "Backrest and knee-rest",
                    "Load Capacity": "180 kg",
                    "Dimensions": "203 x 90 x 60 cm",
                },
            },
            {
                "name": "Basic Surgical Instrument Kit",
                "sku": "MM-SK-001",
                "category": "Surgical Kits",
                "brand": "SterilePro",
                "product_type": Product.ProductType.SURGICAL_EQUIPMENT,
                "short_description": "Reusable stainless-steel surgical instrument kit.",
                "description": "A basic surgical instrument kit with scissors, forceps, needle holder, and tray.",
                "mrp": Decimal("4999.00"),
                "selling_price": Decimal("4299.00"),
                "stock_quantity": 12,
                "manufacturer": "SterilePro Supplies",
                "specifications": {
                    "Material": "Stainless steel",
                    "Sterilizable": "Yes",
                    "Included Items": "Scissors, forceps, needle holder, tray",
                },
            },
            {
                "name": "Laboratory Centrifuge",
                "sku": "MM-CF-001",
                "category": "Centrifuges",
                "brand": "MediSure",
                "product_type": Product.ProductType.DIAGNOSTIC_EQUIPMENT,
                "short_description": "Compact centrifuge for diagnostic sample preparation.",
                "description": "A bench-top laboratory centrifuge suitable for small diagnostic labs and clinics.",
                "mrp": Decimal("21999.00"),
                "selling_price": Decimal("18999.00"),
                "stock_quantity": 6,
                "manufacturer": "MediSure Diagnostics",
                "warranty": "1 Year",
                "specifications": {
                    "Capacity": "8 tubes",
                    "Max Speed": "4000 RPM",
                    "Power": "220V AC",
                    "Timer": "0-30 minutes",
                },
            },
        ]

        for item in products:
            warranty = item.get("warranty", "")
            specifications = item.get("specifications", {})
            product, _ = Product.objects.update_or_create(
                sku=item["sku"],
                defaults={
                    "name": item["name"],
                    "category": created_categories[item["category"]],
                    "brand": brands[item["brand"]],
                    "product_type": item["product_type"],
                    "short_description": item["short_description"],
                    "description": item["description"],
                    "mrp": item["mrp"],
                    "selling_price": item["selling_price"],
                    "stock_quantity": item["stock_quantity"],
                    "requires_prescription": item.get("requires_prescription", False),
                    "manufacturer": item.get("manufacturer", ""),
                    "composition": item.get("composition", ""),
                    "pack_size": item.get("pack_size", ""),
                    "is_active": True,
                    "is_featured": True,
                    "seo_title": f"{item['name']} | MediMart",
                    "seo_description": item["short_description"],
                },
            )
            if warranty:
                ProductSpecification.objects.update_or_create(
                    product=product,
                    name="Warranty",
                    defaults={"value": warranty},
                )
            for name, value in specifications.items():
                ProductSpecification.objects.update_or_create(
                    product=product,
                    name=name,
                    defaults={"value": value},
                )

        self.stdout.write(self.style.SUCCESS("MediMart demo products created."))
