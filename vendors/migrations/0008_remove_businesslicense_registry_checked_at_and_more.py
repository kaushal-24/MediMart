from django.db import migrations, models


def normalize_legacy_api_reviews(apps, schema_editor):
    BusinessLicense = apps.get_model("vendors", "BusinessLicense")
    BusinessLicense.objects.filter(status="api_matched").update(status="manual_review")
    BusinessLicense.objects.filter(verification_source="authorized_api").update(
        verification_source="applicant"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('vendors', '0007_alter_vendor_bank_account_number'),
    ]

    operations = [
        migrations.RunPython(normalize_legacy_api_reviews, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='businesslicense',
            name='registry_checked_at',
        ),
        migrations.RemoveField(
            model_name='businesslicense',
            name='registry_payload',
        ),
        migrations.RemoveField(
            model_name='businesslicense',
            name='registry_reference',
        ),
        migrations.AlterField(
            model_name='businesslicense',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending manual review'), ('manual_review', 'Manual review required'), ('verified', 'Verified'), ('rejected', 'Rejected'), ('expired', 'Expired')], default='pending', max_length=30),
        ),
        migrations.AlterField(
            model_name='businesslicense',
            name='verification_source',
            field=models.CharField(choices=[('applicant', 'Applicant supplied'), ('ondls', 'ONDLS manual verification'), ('cdsco_md', 'CDSCO medical device portal')], default='applicant', max_length=30),
        ),
    ]
