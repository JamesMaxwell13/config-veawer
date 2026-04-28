from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0226_add_mptt_tree_indexes"),
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DevicePlatformProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                (
                    "vendor",
                    models.CharField(
                        choices=[("cisco", "Cisco"), ("dlink", "D-Link")],
                        max_length=16,
                    ),
                ),
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
    ]
