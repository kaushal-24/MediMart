from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0014_bulk_order_review"),
    ]

    operations = [
        migrations.AddField(model_name="shipment", name="carrier_code", field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name="shipment", name="tracking_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="shipment", name="last_location", field=models.CharField(blank=True, max_length=180)),
        migrations.AddField(model_name="shipment", name="exception_reason", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="shipment", name="delivery_attempts", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="shipment", name="cod_collected_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="shipment", name="cod_cash_reference", field=models.CharField(blank=True, max_length=120)),
        migrations.AlterField(
            model_name="shipment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("booked", "Booked"),
                    ("in_transit", "In transit"),
                    ("out_for_delivery", "Out for delivery"),
                    ("delivered", "Delivered"),
                    ("ndr", "Delivery exception"),
                    ("exception", "Exception"),
                    ("returned", "Returned"),
                    ("rto", "Returned to origin"),
                ],
                default="pending",
                max_length=30,
            ),
        ),
    ]
