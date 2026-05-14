import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="gitlabconfigmapping",
            name="actual_backup",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gitlab_actual_mappings",
                to="main.configurationbackup",
            ),
        ),
        migrations.AddField(
            model_name="gitlabconfigmapping",
            name="apply_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="gitlabconfigmapping",
            name="apply_state",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("applying", "Applying"),
                    ("verified", "Verified"),
                    ("drift", "Drift"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="gitlabconfigmapping",
            name="last_apply_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gitlabconfigmapping",
            name="last_apply_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="gitlabconfigmapping",
            name="last_apply_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
