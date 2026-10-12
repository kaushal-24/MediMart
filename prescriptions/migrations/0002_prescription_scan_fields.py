from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("prescriptions", "0002_prescription_doctor_registration_number_and_more")]

    operations = [
        migrations.AddField(
            model_name="prescription",
            name="scan_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="prescription",
            name="scan_flags",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="prescription",
            name="scan_status",
            field=models.CharField(choices=[("pending", "Scan pending"), ("complete", "Technical scan complete"), ("needs_review", "Needs manual review"), ("failed", "Scan failed")], default="pending", max_length=20),
        ),
        migrations.AddField(
            model_name="prescription",
            name="scan_summary",
            field=models.TextField(blank=True),
        ),
    ]
