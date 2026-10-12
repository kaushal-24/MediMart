from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("healthcare", "0006_labreportvalue_explanation_and_more")]

    operations = [
        migrations.DeleteModel(name="CarePlanMembership"),
        migrations.DeleteModel(name="CarePlan"),
    ]
