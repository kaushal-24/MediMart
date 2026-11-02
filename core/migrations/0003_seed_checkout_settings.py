from decimal import Decimal

from django.db import migrations


def seed_checkout_settings(apps, schema_editor):
    checkout_settings = apps.get_model("core", "CheckoutSettings")
    checkout_settings.objects.get_or_create(
        pk=1,
        defaults={
            "delivery_fee": Decimal("49.00"),
            "free_delivery": False,
            "tax_rate_percent": Decimal("18.00"),
            "handling_fee": Decimal("6.00"),
            "platform_fee": Decimal("24.00"),
            "cold_chain_fee": Decimal("1.00"),
            "cod_max_order_value": Decimal("1000.00"),
            "cod_blocked_pincodes": "",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_checkoutsettings"),
    ]

    operations = [
        migrations.RunPython(seed_checkout_settings, migrations.RunPython.noop),
    ]
