from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("healthcare", "0007_remove_care_plan_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultation",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="consultation",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="consultation",
            name="no_show_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="consultation",
            name="provider_session_id",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="consultation",
            name="room_id",
            field=models.CharField(blank=True, max_length=120, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="consultation",
            name="room_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="consultationpayment",
            name="provider_refund_id",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="consultation",
            name="status",
            field=models.CharField(
                choices=[
                    ("requested", "Requested"),
                    ("confirmed", "Confirmed"),
                    ("in_progress", "In progress"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                    ("no_show", "No-show"),
                    ("refund_pending", "Refund pending"),
                ],
                default="requested",
                max_length=20,
            ),
        ),
    ]
