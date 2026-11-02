from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CheckoutSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("delivery_fee", models.DecimalField(decimal_places=2, default=49, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("free_delivery", models.BooleanField(default=False)),
                ("tax_rate_percent", models.DecimalField(decimal_places=2, default=0, max_digits=5, validators=[django.core.validators.MinValueValidator(0)])),
                ("handling_fee", models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("platform_fee", models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("cold_chain_fee", models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("cod_max_order_value", models.DecimalField(decimal_places=2, default=5000, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("cod_blocked_pincodes", models.TextField(blank=True, help_text="Enter blocked 6-digit pincodes separated by commas or new lines.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="updated_checkout_settings", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "checkout settings", "verbose_name_plural": "checkout settings"},
        ),
    ]
