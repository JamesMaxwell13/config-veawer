from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0226_add_mptt_tree_indexes"),
        ("main", "0003_rename_business_task"),
    ]

    operations = [
        migrations.AddField(
            model_name="devicecredential",
            name="auth_method",
            field=models.CharField(choices=[("password", "Username/Password")], default="password", max_length=32),
        ),
        migrations.AddField(
            model_name="devicecredential",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="commandtemplate",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="commandtemplate",
            name="revision",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="networkscenario",
            name="plan_format",
            field=models.CharField(choices=[("yaml", "YAML")], default="yaml", max_length=16),
        ),
        migrations.AddField(
            model_name="networkscenario",
            name="plan_checksum",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="networkscenario",
            name="last_validated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="configurationbackup",
            name="config_checksum",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="configurationbackup",
            name="redacted",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="deviceplatformprofile",
            name="command_timeout",
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AddField(
            model_name="scheduledtask",
            name="max_retries",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="scheduledtask",
            name="retry_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="UMLConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=150)),
                (
                    "diagram_type",
                    models.CharField(
                        choices=[("plantuml", "PlantUML"), ("mermaid", "Mermaid"), ("json", "JSON")],
                        default="plantuml",
                        max_length=16,
                    ),
                ),
                ("source_text", models.TextField()),
                ("rendered_svg", models.TextField(blank=True)),
                ("checksum", models.CharField(blank=True, max_length=64)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "device",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="uml_configurations", to="dcim.device"),
                ),
                (
                    "scenario",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="uml_configurations", to="main.networkscenario"),
                ),
            ],
            options={"ordering": ("name", "-revision")},
        ),
        migrations.AlterUniqueTogether(name="umlconfiguration", unique_together={("name", "revision")}),
    ]
