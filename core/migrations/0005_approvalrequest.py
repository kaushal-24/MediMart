from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0004_checkoutsettings_business_state_and_more")]

    operations = [
        migrations.CreateModel(
            name="ApprovalRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_id", models.PositiveBigIntegerField()),
                ("action", models.CharField(max_length=80)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", max_length=20)),
                ("request_reason", models.TextField(blank=True)),
                ("decision_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("content_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="contenttypes.contenttype")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="approval_requests", to=settings.AUTH_USER_MODEL)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="approval_decisions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["status", "created_at"], "indexes": [models.Index(fields=["status", "created_at"], name="approval_status_created_idx")]},
        ),
        migrations.AddConstraint(
            model_name="approvalrequest",
            constraint=models.UniqueConstraint(fields=["content_type", "object_id", "action", "status"], name="approval_target_action_status_unique"),
        ),
    ]
