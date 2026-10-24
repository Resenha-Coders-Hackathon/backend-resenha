from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_workspace_onboarding")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="location",
            field=models.JSONField(
                blank=True, default=None, null=True, verbose_name="location"
            ),
        ),
    ]
