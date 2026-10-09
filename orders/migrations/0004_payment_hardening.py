from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_order_order_customer_created_idx_and_more")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="inventory_released_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="stock_reserved_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("authorized", "Authorized"),
                    ("paid", "Paid"),
                    ("failed", "Failed"),
                    ("partially_refunded", "Partially Refunded"),
                    ("refunded", "Refunded"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(model_name="payment", name="captured_amount", field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.AddField(model_name="payment", name="currency", field=models.CharField(default="INR", max_length=3)),
        migrations.AddField(model_name="payment", name="failure_code", field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name="payment", name="failure_description", field=models.CharField(blank=True, max_length=500)),
        migrations.AddField(model_name="payment", name="gateway_metadata", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="payment", name="gateway_order_id", field=models.CharField(blank=True, max_length=80, null=True, unique=True)),
        migrations.AddField(model_name="payment", name="gateway_payment_id", field=models.CharField(blank=True, max_length=80, null=True, unique=True)),
        migrations.AddField(model_name="payment", name="gateway_signature", field=models.CharField(blank=True, max_length=160)),
        migrations.AddField(model_name="payment", name="gateway_status", field=models.CharField(blank=True, max_length=30)),
        migrations.AddField(model_name="payment", name="last_gateway_check_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="payment", name="refunded_amount", field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.AddField(model_name="payment", name="verified_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(
            name="PaymentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(max_length=120, unique=True)),
                ("event_type", models.CharField(max_length=80)),
                ("payload_hash", models.CharField(max_length=64, unique=True)),
                ("gateway_order_id", models.CharField(blank=True, max_length=80)),
                ("gateway_payment_id", models.CharField(blank=True, max_length=80)),
                ("processed", models.BooleanField(default=False)),
                ("processing_error", models.CharField(blank=True, max_length=500)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-received_at"],
                "indexes": [models.Index(fields=["event_type", "-received_at"], name="payment_event_type_idx")],
            },
        ),
    ]
