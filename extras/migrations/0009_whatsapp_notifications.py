from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("extras", "0008_qualitycomplaint_pharmacistprofile")]
    operations = [
        migrations.AlterField(
            model_name="notificationdelivery",
            name="channel",
            field=models.CharField(choices=[("whatsapp", "WhatsApp"), ("email", "Legacy email (disabled)")], max_length=20),
        ),
    ]
