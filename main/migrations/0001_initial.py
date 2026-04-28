from django.db import migrations, models
import django.db.models.deletion
import taggit.managers
import utilities.json


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("dcim", "0226_add_mptt_tree_indexes"),
        ("extras", "0134_owner"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommandTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
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
                ("is_active", models.BooleanField(default=True)),
                ("revision", models.PositiveIntegerField(default=1)),
            ],
            options={"ordering": ("vendor", "platform", "operation_type", "name")},
        ),
        migrations.CreateModel(
            name="DeviceCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("auth_method", models.CharField(choices=[("password", "Username/Password")], default="password", max_length=32)),
                ("username", models.CharField(max_length=128)),
                ("password", models.CharField(max_length=255)),
                ("enable_secret", models.CharField(blank=True, max_length=255)),
                ("ssh_port", models.PositiveIntegerField(default=22)),
                ("timeout", models.PositiveIntegerField(default=30)),
                ("use_enable", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="NetworkTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.TextField(blank=True)),
                ("device_task", models.CharField(max_length=255)),
                ("plan_format", models.CharField(choices=[("yaml", "YAML")], default="yaml", max_length=16)),
                ("plan_yaml", models.TextField()),
                ("plan_checksum", models.CharField(blank=True, max_length=64)),
                ("enabled", models.BooleanField(default=True)),
                ("last_validated_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="ConfigurationBackup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
                ("version", models.PositiveIntegerField(default=1)),
                ("version_name", models.CharField(blank=True, max_length=128)),
                ("config_text", models.TextField()),
                ("source", models.CharField(default="runtime", max_length=64)),
                ("commit_hash", models.CharField(blank=True, max_length=64)),
                ("config_checksum", models.CharField(blank=True, max_length=64)),
                ("redacted", models.BooleanField(default=True)),
                (
                    "device",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="config_backups", to="dcim.device"),
                ),
                (
                    "task",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="backups", to="main.networktask"),
                ),
            ],
            options={"ordering": ("-created",)},
        ),
        migrations.CreateModel(
            name="DevicePlatformProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
                ("vendor", models.CharField(choices=[("cisco", "Cisco"), ("dlink", "D-Link")], max_length=16)),
                (
                    "platform",
                    models.CharField(
                        choices=[
                            ("cisco_ios", "Cisco IOS"),
                            ("cisco_xe", "Cisco IOS-XE"),
                            ("cisco_nxos", "Cisco NX-OS"),
                            ("dlink_ds", "D-Link DS"),
                            ("dlink_dgs", "D-Link DGS"),
                        ],
                        max_length=32,
                    ),
                ),
                ("management_ip", models.GenericIPAddressField(blank=True, null=True, protocol="IPv4")),
                ("command_timeout", models.PositiveIntegerField(default=60)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "credential",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="device_profiles", to="main.devicecredential"),
                ),
                (
                    "device",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="config_weaver_profile", to="dcim.device"),
                ),
            ],
            options={"ordering": ("device",)},
        ),
        migrations.CreateModel(
            name="ScheduledTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
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
                ("max_retries", models.PositiveIntegerField(default=0)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                (
                    "target_device",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scheduled_tasks", to="dcim.device"),
                ),
                (
                    "task",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scheduled_tasks", to="main.networktask"),
                ),
            ],
            options={"ordering": ("schedule_time",)},
        ),
        migrations.CreateModel(
            name="UMLConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
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
                    "task",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="uml_configurations", to="main.networktask"),
                ),
            ],
            options={"ordering": ("name", "-revision")},
        ),
        migrations.AlterUniqueTogether(name="commandtemplate", unique_together={("name", "vendor", "platform", "operation_type")}),
        migrations.AlterUniqueTogether(name="configurationbackup", unique_together={("device", "version")}),
        migrations.AlterUniqueTogether(name="umlconfiguration", unique_together={("name", "revision")}),
    ]
