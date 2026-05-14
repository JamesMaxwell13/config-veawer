from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dcim.choices import InterfaceModeChoices, InterfaceTypeChoices
from dcim.models import Device, DeviceRole, DeviceType, Interface, Manufacturer, Site
from django.test import TestCase, override_settings
from ipam.models import VLAN

from main.application.configuration_yaml import ConfigurationYamlService
from main.application.interface_sync import InterfaceSyncService
from main.infrastructure.vcs import ConfigurationVCS
from main.models import ConfigurationBackup, DeviceCredential, DevicePlatformProfile


def create_device(name: str = "sync-sw1") -> Device:
    manufacturer = Manufacturer.objects.create(name=f"{name} manufacturer", slug=f"{name}-manufacturer")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model=f"{name} type", slug=f"{name}-type")
    role = DeviceRole.objects.create(name=f"{name} role", slug=f"{name}-role")
    site = Site.objects.create(name=f"{name} site", slug=f"{name}-site")
    return Device.objects.create(site=site, device_type=device_type, role=role, name=name)


@override_settings(
    PLUGINS_CONFIG={
        "main": {
            "secret_key": "test-secret-key",
            "auto_sync_on_netbox_change": False,
            "auto_sync_from_config": True,
            "auto_push_manual_backups": True,
        }
    }
)
class InterfaceSyncTests(TestCase):
    def setUp(self):
        self.device = create_device()
        self.vlan10 = VLAN.objects.create(site=self.device.site, vid=10, name="Users")
        self.vlan20 = VLAN.objects.create(site=self.device.site, vid=20, name="Voice")
        self.iface = Interface.objects.create(
            device=self.device,
            name="GigabitEthernet0/1",
            type=InterfaceTypeChoices.TYPE_1GE_FIXED,
        )

    def test_sync_from_configuration_updates_device_and_interface_parameters(self):
        yaml_text = ConfigurationYamlService.dump_yaml(
            {
                "schema_version": 2,
                "device": {"id": self.device.pk, "name": self.device.name},
                "platform": "cisco_ios",
                "source": "gitlab",
                "operations": [
                    {"name": "hostname", "operation_type": "custom", "params": {"hostname": "sync-sw1-new"}},
                    {"name": "interface_no_shutdown", "operation_type": "interface", "params": {"interface": "Gi0/1"}},
                    {"name": "interface_description", "operation_type": "interface", "params": {"interface": "Gi0/1", "description": "Uplink"}},
                    {"name": "switchport_mode_access", "operation_type": "vlan", "params": {"interface": "Gi0/1"}},
                    {"name": "switchport_access_vlan", "operation_type": "vlan", "params": {"interface": "Gi0/1", "vlan_id": "10"}},
                    {"name": "mtu", "operation_type": "interface", "params": {"interface": "Gi0/1", "mtu": "1500"}},
                    {"name": "speed", "operation_type": "interface", "params": {"interface": "Gi0/1", "speed": "1000"}},
                    {"name": "duplex", "operation_type": "interface", "params": {"interface": "Gi0/1", "duplex": "full"}},
                ],
                "sections": [],
                "raw_commands": [],
            }
        )
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="gitlab-sync",
            config_text=yaml_text,
            source="gitlab",
            config_checksum=ConfigurationYamlService.checksum(yaml_text),
        )

        result = InterfaceSyncService.sync_from_configuration_backup(backup, origin="test")

        self.assertEqual(result["status"], "success")
        self.device.refresh_from_db()
        self.iface.refresh_from_db()
        self.assertEqual(self.device.name, "sync-sw1-new")
        self.assertTrue(self.iface.enabled)
        self.assertEqual(self.iface.description, "Uplink")
        self.assertEqual(self.iface.mode, InterfaceModeChoices.MODE_ACCESS)
        self.assertEqual(self.iface.untagged_vlan_id, self.vlan10.pk)
        self.assertEqual(self.iface.mtu, 1500)
        self.assertEqual(self.iface.speed, 1000000)
        self.assertEqual(self.iface.duplex, "full")

    def test_sync_from_netbox_applies_then_pushes_to_gitlab(self):
        credential = DeviceCredential.objects.create(name="sync-cred", username="admin", password="password")
        DevicePlatformProfile.objects.create(
            device=self.device,
            credential=credential,
            vendor=DevicePlatformProfile.VENDOR_CISCO,
            platform=DevicePlatformProfile.PLATFORM_CISCO_IOS,
            management_ip="192.0.2.10",
            enabled=True,
        )
        self.iface.mode = InterfaceModeChoices.MODE_ACCESS
        self.iface.untagged_vlan = self.vlan20
        self.iface.enabled = True
        self.iface.description = "Edge"
        self.iface.mtu = 1500
        self.iface.speed = 1000000
        self.iface.duplex = "full"
        self.iface.save()

        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=2,
            version_name="runtime",
            config_text="schema_version: 2\noperations: []\n",
            source="runtime",
            config_checksum="x",
        )
        events: list[str] = []

        with (
            patch("main.application.interface_sync.InterfaceSyncService.should_sync_on_netbox_change", return_value=True),
            patch("main.application.interface_sync.TaskExecutor.apply_yaml_to_device", side_effect=lambda *_a, **_k: events.append("apply")),
            patch("main.application.interface_sync.ConfigurationRepository.latest_backup_for_device", return_value=backup),
            patch("main.application.gitlab.GitLabIntegrationService.push_backup_to_gitlab", side_effect=lambda *_a, **_k: events.append("push")),
        ):
            result = InterfaceSyncService.sync_from_netbox_device(self.device, origin="test")

        self.assertEqual(result["status"], "success")
        self.assertEqual(events, ["apply", "push"])

    def test_manual_backup_creation_auto_pushes_to_gitlab(self):
        with TemporaryDirectory() as tmpdir:
            with (
                patch.object(ConfigurationVCS, "repo_path", return_value=Path(tmpdir)),
                patch("main.infrastructure.vcs.subprocess.run"),
                patch("main.infrastructure.vcs.subprocess.check_output", return_value=b"abc123\n"),
                patch("main.application.gitlab.GitLabIntegrationService.push_backup_to_gitlab") as push,
            ):
                ConfigurationVCS.write_backup(
                    device=self.device,
                    config_text="hostname sync-sw1",
                    source="manual_cli",
                )

        push.assert_called_once()
