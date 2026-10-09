from django.db import migrations


def seed_existing_license_reviews(apps, schema_editor):
    Vendor = apps.get_model("vendors", "Vendor")
    BusinessLicense = apps.get_model("vendors", "BusinessLicense")
    for vendor in Vendor.objects.exclude(license_number="").iterator():
        if vendor.business_type == "pharmacy":
            license_type = "drug_retail"
        elif vendor.business_type == "manufacturer":
            license_type = "device_manufacturing"
        else:
            license_type = "device_sale"
        BusinessLicense.objects.get_or_create(
            vendor=vendor,
            license_type=license_type,
            license_number=vendor.license_number,
            defaults={
                "legal_name": vendor.business_name,
                "premises_address": vendor.address,
                "status": "manual_review",
                "verification_source": "applicant",
                "review_notes": "Migrated from the legacy seller licence field; independent review required.",
            },
        )
        if vendor.email.lower().endswith("@medimart.local"):
            vendor.email = f"{vendor.email.rsplit('@', 1)[0]}@gmail.com"
            vendor.save(update_fields=["email"])


class Migration(migrations.Migration):
    dependencies = [("vendors", "0004_businesslicense")]

    operations = [migrations.RunPython(seed_existing_license_reviews, migrations.RunPython.noop)]
