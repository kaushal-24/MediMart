from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0013_return_workflow"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="BulkOrderReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("threshold", models.PositiveIntegerField(default=10)),
                ("status", models.CharField(choices=[("pending", "Pending verification"), ("approved", "Approved"), ("rejected", "Rejected"), ("clarification", "Customer clarification needed")], default="pending", max_length=20)),
                ("review_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="bulk_review", to="orders.order")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bulk_order_reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["status", "created_at"], "indexes": [models.Index(fields=["status", "created_at"], name="bulk_review_status_idx")]},
        ),
    ]
