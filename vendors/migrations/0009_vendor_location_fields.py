from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("vendors", "0008_remove_businesslicense_registry_checked_at_and_more")]
    operations = [
        migrations.AddField("vendor", "city", models.CharField(blank=True, max_length=100)),
        migrations.AddField("vendor", "state", models.CharField(blank=True, max_length=100)),
        migrations.AddField("vendor", "pincode", models.CharField(blank=True, max_length=6)),
        migrations.AddField("vendor", "latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField("vendor", "longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddIndex("vendor", models.Index(fields=["pincode", "business_type", "is_active"], name="vendor_location_idx")),
    ]
