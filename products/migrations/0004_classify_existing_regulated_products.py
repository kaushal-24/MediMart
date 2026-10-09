from django.db import migrations


def classify_existing_products(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Product.objects.filter(product_type="medicine").update(
        requires_business_license=True,
        required_license_type="drug_sale",
    )
    Product.objects.filter(
        product_type__in=[
            "medical_equipment",
            "surgical_equipment",
            "diagnostic_equipment",
            "lab_equipment",
        ]
    ).update(
        requires_business_license=True,
        required_license_type="medical_device_sale",
    )


class Migration(migrations.Migration):
    dependencies = [("products", "0003_product_regulatory_classification_and_more")]

    operations = [migrations.RunPython(classify_existing_products, migrations.RunPython.noop)]
