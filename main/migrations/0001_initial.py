from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("dcim", "0226_add_mptt_tree_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommandTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=100)),
                ("vendor", models.CharField(max_length=100)),
                ("platform", models.CharField(max_length=100)),
                (
                    "operation_type",
                    models.CharField(
                        choices=[
                            ("interface", "Interface config"),
                            ("vlan", "VLAN config"),
                            ("ip", "IP config"),
                            ("custom", "Custom"),
                        ],
                        default="custom",
                        max_length=32,
                    ),
                ),
                ("command_body", models.TextField()),
            ],
            options={"ordering": ("vendor", "platform", "operation_type", "name")},
        ),
        migrations.CreateModel(
            name="DeviceCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("username", models.CharField(max_length=128)),
                ("password", models.CharField(max_length=255)),
                ("enable_secret", models.CharField(blank=True, max_length=255)),
                ("ssh_port", models.PositiveIntegerField(default=22)),
                ("timeout", models.PositiveIntegerField(default=30)),
                ("use_enable", models.BooleanField(default=False)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="NetworkScenario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("business_task", models.CharField(max_length=255)),
                ("plan_yaml", models.TextField()),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="ConfigurationBackup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                ("version", models.PositiveIntegerField(default=1)),
                ("config_text", models.TextField()),
                ("source", models.CharField(default="runtime", max_length=64)),
                ("commit_hash", models.CharField(blank=True, max_length=64)),
                (
                    "device",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="config_backups", to="dcim.device"),
                ),
                (
                    "scenario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="backups",
                        to="main.networkscenario",
                    ),
                ),
            ],
            options={"ordering": ("-created",)},
        ),
        migrations.CreateModel(
            name="ScheduledTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                ("task_name", models.CharField(max_length=150)),
                (
                    "task_type",
                    models.CharField(
                        choices=[
                            ("apply_scenario", "Apply scenario"),
                            ("backup", "Create backup"),
                            ("healthcheck", "Health check"),
                        ],
                        max_length=40,
                    ),
                ),
                ("schedule_time", models.DateTimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("result_message", models.TextField(blank=True)),
                ("run_every_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                (
                    "scenario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scheduled_tasks",
                        to="main.networkscenario",
                    ),
                ),
                (
                    "target_device",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduled_tasks", to="dcim.device"),
                ),
            ],
            options={"ordering": ("schedule_time",)},
        ),
        migrations.AlterUniqueTogether(name="commandtemplate", unique_together={("name", "vendor", "platform", "operation_type")}),
        migrations.AlterUniqueTogether(name="configurationbackup", unique_together={("device", "version")}),
    ]
