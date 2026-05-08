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
                            ("apply_scenario", "Применить сценарий"),
                            ("backup", "Сохранить конфигурацию"),
                            ("healthcheck", "Проверить подключение"),
                        ],
                        max_length=40,
                    ),
                ),
                ("task", models.TextField(blank=True, verbose_name="Таск (YAML)")),
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
        migrations.CreateModel(
            name="GitLabIntegration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("gitlab_url", models.URLField()),
                ("project_id", models.CharField(max_length=255)),
                ("branch", models.CharField(default="main", max_length=255)),
                ("root_path", models.CharField(default="configs", max_length=255)),
                (
                    "file_path_pattern",
                    models.CharField(
                        default="{root_path}/{site_slug}/{location_slug}/{rack_slug}/{device_name}.yaml",
                        max_length=512,
                    ),
                ),
                ("access_token", models.CharField(max_length=512)),
                ("webhook_secret", models.CharField(blank=True, max_length=512)),
                ("enabled", models.BooleanField(default=True)),
                ("auto_apply", models.BooleanField(default=False)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "GitLab integration",
                "verbose_name_plural": "GitLab integrations",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="GitLabConfigMapping",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
                ("file_path", models.CharField(max_length=1024)),
                ("last_gitlab_commit_sha", models.CharField(blank=True, max_length=64)),
                ("last_plugin_update_at", models.DateTimeField(blank=True, null=True)),
                ("last_gitlab_update_at", models.DateTimeField(blank=True, null=True)),
                ("sync_enabled", models.BooleanField(default=True)),
                (
                    "configuration_backup",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gitlab_mappings",
                        to="main.configurationbackup",
                    ),
                ),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gitlab_config_mappings",
                        to="dcim.device",
                    ),
                ),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="config_mappings",
                        to="main.gitlabintegration",
                    ),
                ),
                (
                    "scheduled_task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gitlab_mappings",
                        to="main.scheduledtask",
                    ),
                ),
            ],
            options={
                "verbose_name": "GitLab config mapping",
                "verbose_name_plural": "GitLab config mappings",
                "ordering": ("integration", "file_path"),
                "unique_together": {("integration", "device"), ("integration", "file_path")},
            },
        ),
        migrations.CreateModel(
            name="GitLabSyncLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
                ("direction", models.CharField(choices=[("gitlab_to_plugin", "GitLab to plugin"), ("plugin_to_gitlab", "Plugin to GitLab")], max_length=32)),
                ("file_path", models.CharField(blank=True, max_length=1024)),
                ("commit_sha", models.CharField(blank=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("success", "Success"), ("failed", "Failed"), ("skipped", "Skipped"), ("conflict", "Conflict")],
                        max_length=16,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "configuration_backup",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gitlab_sync_logs",
                        to="main.configurationbackup",
                    ),
                ),
                (
                    "device",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gitlab_sync_logs",
                        to="dcim.device",
                    ),
                ),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sync_logs",
                        to="main.gitlabintegration",
                    ),
                ),
                (
                    "mapping",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sync_logs",
                        to="main.gitlabconfigmapping",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gitlab_sync_logs",
                        to="main.scheduledtask",
                    ),
                ),
            ],
            options={
                "verbose_name": "GitLab sync log",
                "verbose_name_plural": "GitLab sync logs",
                "ordering": ("-created",),
            },
        ),
        migrations.AlterUniqueTogether(name="commandtemplate", unique_together={("name", "vendor", "platform", "operation_type")}),
        migrations.AlterUniqueTogether(name="configurationbackup", unique_together={("device", "version")}),
        migrations.AlterUniqueTogether(name="umlconfiguration", unique_together={("name", "revision")}),
    ]
