from django.conf import settings
from django.db import migrations


def convert_local_demo_emails(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    for user in User.objects.filter(email__iendswith="@medimart.local").iterator():
        local_part = user.email.rsplit("@", 1)[0]
        user.email = f"{local_part}@gmail.com"
        user.save(update_fields=["email"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_address_country_address_country_code_and_more"),
    ]

    operations = [migrations.RunPython(convert_local_demo_emails, migrations.RunPython.noop)]
