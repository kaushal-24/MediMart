from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("extras", "0011_assistantfeedback")]

    operations = [
        migrations.AlterField(
            model_name="notificationdelivery",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                    ("dead_letter", "Dead letter"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
