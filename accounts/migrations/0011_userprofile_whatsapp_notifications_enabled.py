from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_usercapabilityoverride")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="whatsapp_notifications_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
