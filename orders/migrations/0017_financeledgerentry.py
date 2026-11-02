from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("orders", "0016_orderchargebreakdown_cgst_amount_and_more")]

    operations = [
        migrations.CreateModel(
            name="FinanceLedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entry_reference", models.CharField(max_length=160, unique=True)),
                ("entry_type", models.CharField(choices=[("payment", "Payment"), ("refund", "Refund"), ("tax", "Tax"), ("fee", "Fee"), ("commission", "Commission"), ("cod_collection", "COD collection"), ("settlement", "Settlement"), ("chargeback", "Chargeback"), ("credit_note", "Credit note")], max_length=30)),
                ("direction", models.CharField(choices=[("credit", "Credit"), ("debit", "Debit")], max_length=10)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(default="INR", max_length=3)),
                ("description", models.CharField(max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("finance_test_mode", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="finance_ledger_entries", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="orders.order")),
                ("payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="orders.payment")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="financeledgerentry",
            constraint=models.CheckConstraint(condition=models.Q(amount__gt=0), name="finance_ledger_amount_positive"),
        ),
        migrations.AddIndex(
            model_name="financeledgerentry",
            index=models.Index(fields=["entry_type", "-created_at"], name="finance_ledger_type_idx"),
        ),
        migrations.AddIndex(
            model_name="financeledgerentry",
            index=models.Index(fields=["order", "-created_at"], name="finance_ledger_order_idx"),
        ),
    ]
