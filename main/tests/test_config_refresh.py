from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from users.models import User

from main.application.backups import ConfigurationService
from main.application.configuration_yaml import ConfigurationYamlService
from main.application.tasks import TaskExecutor
from main.domain.configuration import ConfigValidationError
from main.domain.security import redact_secrets
from main.infrastructure.vcs import ConfigurationVCS
from main.models import CommandTemplate, ConfigurationBackup, DeviceCredential, DevicePlatformProfile, ScheduledTask


def create_device(name="refresh-sw1"):
    manufacturer = Manufacturer.objects.create(name=f"{name} manufacturer", slug=f"{name}-manufacturer")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model=f"{name} type", slug=f"{name}-type")
    role = DeviceRole.objects.create(name=f"{name} role", slug=f"{name}-role")
    site = Site.objects.create(name=f"{name} site", slug=f"{name}-site")
    return Device.objects.create(site=site, device_type=device_type, role=role, name=name)


@override_settings(PLUGINS_CONFIG={"main": {"secret_key": "test-secret-key"}})
class ConfigurationRefreshTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.device = create_device()
        self.credential = DeviceCredential.objects.create(
            name="refresh-cred",
            username="admin",
            password="password",
        )
        self.profile = DevicePlatformProfile.objects.create(
            device=self.device,
            credential=self.credential,
            vendor=DevicePlatformProfile.VENDOR_CISCO,
            platform=DevicePlatformProfile.PLATFORM_CISCO_IOS,
            management_ip="192.0.2.20",
            enabled=True,
        )
        self.client.force_login(self.user)

    def _mock_session(self, config_text):
        session = MagicMock()
        session.get_running_config.return_value = config_text
        return session

    def test_refresh_new_device_creates_initial_backup(self):
        session = self._mock_session("hostname refresh-sw1")

        with TemporaryDirectory() as tmpdir:
            with (
                patch("main.application.backups.connect_device_cli", return_value=(session, self.profile, {"checked": False})),
                patch.object(ConfigurationVCS, "repo_path", return_value=Path(tmpdir)),
                patch("main.infrastructure.vcs.subprocess.run"),
                patch("main.infrastructure.vcs.subprocess.check_output", return_value=b"abc123\n"),
            ):
                result = ConfigurationService.refresh_device_config(self.device)

        self.assertTrue(result["changed"])
        self.assertEqual(result["reason"], "no_backup")
        self.assertEqual(result["backup"].version, 1)
        self.assertEqual(result["backup"].source, "manual_refresh")
        self.assertTrue(ConfigurationYamlService.is_yaml_config(result["backup"].config_text))
        self.assertIn("raw_commands:", result["backup"].config_text)
        session.disconnect.assert_called_once()

    def test_refresh_unchanged_config_does_not_create_backup(self):
        config = "hostname refresh-sw1"
        checksum = __import__("hashlib").sha256(redact_secrets(config).encode("utf-8")).hexdigest()
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text=config,
            source="runtime",
            config_checksum=checksum,
        )
        session = self._mock_session(config)

        with patch("main.application.backups.connect_device_cli", return_value=(session, self.profile, {"checked": False})):
            result = ConfigurationService.refresh_device_config(self.device, compare_to=backup)

        self.assertFalse(result["changed"])
        self.assertEqual(result["backup"], backup)
        self.assertEqual(ConfigurationBackup.objects.count(), 1)
        session.disconnect.assert_called_once()

    def test_configuration_page_has_refresh_button(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text="hostname refresh-sw1",
            source="runtime",
            commit_hash="abcdef1234567890",
            config_checksum="checksum",
        )

        response = self.client.get(backup.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("plugins:main:configurationbackup_refresh", kwargs={"pk": backup.pk}),
        )
        self.assertContains(response, "Validate configuration")
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_versions", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, 'title="abcdef1234567890"')
        self.assertContains(response, ">abcdef123456</code>")
        self.assertContains(response, 'title="checksum"')
        self.assertContains(response, "btn-success")
        self.assertNotContains(response, "btn-warning")

    def test_configuration_page_renders_yaml_inline(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="v1",
            config_text="hostname refresh-sw1\ninterface Ethernet0/0",
            source="runtime",
            config_checksum="checksum",
        )

        response = self.client.get(backup.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "View YAML")
        self.assertContains(response, "version_name: v1")
        self.assertContains(response, "config_checksum: checksum")
        self.assertContains(response, "config: |")
        self.assertContains(response, "hostname refresh-sw1")

    def test_configuration_yaml_view_renders_backup_as_yaml(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="v1",
            config_text="hostname refresh-sw1\ninterface Ethernet0/0",
            source="runtime",
            commit_hash="abc123",
            config_checksum="checksum",
            redacted=True,
        )

        response = self.client.get(reverse("plugins:main:configurationbackup_yaml", kwargs={"pk": backup.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "version_name: v1")
        self.assertContains(response, "config_checksum: checksum")
        self.assertContains(response, "config: |")
        self.assertContains(response, "hostname refresh-sw1")

    def test_configuration_list_links_to_backup_detail(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="baseline",
            config_text="hostname refresh-sw1",
            source="runtime",
            commit_hash="abcdef1234567890",
            config_checksum="1234567890abcdef",
        )

        response = self.client.get(reverse("plugins:main:configurationbackup_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, backup.get_absolute_url())
        self.assertContains(response, ">baseline</a>")
        self.assertNotContains(response, '>Open</a>')
        self.assertContains(response, 'title="abcdef1234567890"')
        self.assertContains(response, ">abcdef123456</code>")
        self.assertContains(response, 'title="1234567890abcdef"')
        self.assertContains(response, ">1234567890ab</code>")

    def test_profile_page_renders_config_weaver_profile(self):
        response = self.client.get(self.profile.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Available commands")
        self.assertContains(response, "Device profile")
        self.assertNotContains(response, "Device CLI")
        self.assertNotContains(response, "Recent configurations")
        self.assertContains(response, self.device.name)
        self.assertContains(response, self.credential.name)
        self.assertContains(response, "Cisco")
        self.assertContains(response, "Cisco IOS")
        self.assertContains(response, "192.0.2.20")
        self.assertContains(response, "60")
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_versions", kwargs={"pk": self.profile.pk}),
        )

    def test_device_configurations_page_has_get_config_button(self):
        response = self.client.get(reverse("dcim:device_configurations", kwargs={"pk": self.device.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_refresh_config", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, "Refresh configuration")

    def test_device_get_config_redirects_to_created_configuration(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text="hostname refresh-sw1",
            source="manual_refresh",
            config_checksum="created-checksum",
        )

        with patch.object(
            ConfigurationService,
            "refresh_device_config",
            return_value={"changed": True, "backup": backup},
        ) as refresh:
            response = self.client.post(
                reverse("plugins:main:deviceplatformprofile_refresh_config", kwargs={"pk": self.profile.pk})
            )

        refresh.assert_called_once_with(self.device)
        self.assertRedirects(response, backup.get_absolute_url(), fetch_redirect_response=False)

    def test_configuration_form_rejects_invalid_ip_and_mask(self):
        before = ConfigurationBackup.objects.count()
        response = self.client.post(
            reverse("plugins:main:configurationbackup_add"),
            {
                "device": self.device.pk,
                "task": "",
                "version": "",
                "version_name": "invalid-ip-mask",
                "config_text": "interface GigabitEthernet0/1\n ip address 10.0.0.999 255.0.255.0\n",
                "source": "manual",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid IPv4 address")
        self.assertEqual(ConfigurationBackup.objects.count(), before)

    def test_configuration_api_rejects_invalid_ip_and_mask(self):
        before = ConfigurationBackup.objects.count()
        response = self.client.post(
            "/api/plugins/config-weaver/configurations/",
            data=json.dumps(
                {
                    "device": self.device.pk,
                    "version": 1,
                    "version_name": "invalid-api",
                    "config_text": "interface GigabitEthernet0/1\n ip address 10.10.10.999 255.0.255.0\n",
                    "source": "manual",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid IPv4 address", response.content.decode("utf-8"))
        self.assertEqual(ConfigurationBackup.objects.count(), before)

    def test_device_get_config_redirects_to_existing_configuration_when_unchanged(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text="hostname refresh-sw1",
            source="runtime",
            config_checksum="existing-checksum",
        )

        with patch.object(
            ConfigurationService,
            "refresh_device_config",
            return_value={"changed": False, "backup": backup},
        ) as refresh:
            response = self.client.post(
                reverse("plugins:main:deviceplatformprofile_refresh_config", kwargs={"pk": self.profile.pk})
            )

        refresh.assert_called_once_with(self.device)
        self.assertRedirects(response, backup.get_absolute_url(), fetch_redirect_response=False)

    def test_apply_yaml_to_device_rejects_invalid_ip_and_mask_before_connect(self):
        yaml_text = ConfigurationYamlService.dump_yaml(
            {
                "schema_version": 2,
                "device": {"id": self.device.pk, "name": self.device.name},
                "platform": self.profile.platform,
                "source": "runtime",
                "operations": [],
                "sections": [],
                "raw_commands": [
                    "interface GigabitEthernet0/1",
                    "ip address 10.0.0.999 255.0.255.0",
                ],
            }
        )
        with (
            self.assertRaises(ConfigValidationError),
            patch("main.application.tasks.connect_device_cli") as connect_device_cli,
        ):
            TaskExecutor.apply_yaml_to_device(self.device, yaml_text)
        connect_device_cli.assert_not_called()

    def test_device_configurations_page_shows_current_and_previous_versions(self):
        ConfigurationBackup.objects.create(
            device=self.device,
            version=2,
            version_name="current",
            config_text=ConfigurationYamlService.running_config_to_yaml(
                self.device,
                "hostname current",
                source="runtime",
            ),
            source="runtime",
            config_checksum="current-checksum",
        )
        previous = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="previous",
            config_text=ConfigurationYamlService.running_config_to_yaml(
                self.device,
                "hostname previous",
                source="runtime",
            ),
            source="runtime",
            config_checksum="previous-checksum",
        )

        response = self.client.get(reverse("dcim:device_configurations", kwargs={"pk": self.device.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current configuration")
        self.assertContains(response, "v2")
        self.assertContains(response, "current")
        self.assertContains(response, "Previous configurations")
        self.assertContains(response, "previous")
        self.assertContains(
            response,
            reverse("plugins:main:configurationbackup_restore", kwargs={"pk": previous.pk}),
        )
        self.assertContains(response, "Apply to device")
        self.assertContains(response, "btn-success")
        self.assertNotContains(response, "Device CLI")
        self.assertNotContains(response, "Upcoming scheduled tasks")

    def test_legacy_configuration_versions_url_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("plugins:main:configuration_versions", kwargs={"device_id": self.device.pk})

    def test_configuration_versions_tab_marks_current_and_can_send_previous(self):
        current = ConfigurationBackup.objects.create(
            device=self.device,
            version=2,
            version_name="current",
            config_text="hostname current",
            source="runtime",
            config_checksum="current-checksum",
        )
        previous = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="previous",
            config_text="hostname previous",
            source="runtime",
            config_checksum="previous-checksum",
        )

        response = self.client.get(reverse("plugins:main:deviceplatformprofile_versions", kwargs={"pk": self.profile.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configuration versions")
        self.assertContains(response, "configuration-compare-form")
        self.assertContains(response, 'type="checkbox" value=', count=2)
        self.assertContains(response, "<th>Source</th>", html=True)
        self.assertContains(response, "<td>runtime</td>", html=True, count=2)
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_versions_diff", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, "Latest stored")
        self.assertContains(response, "Apply", count=1)
        self.assertContains(response, "btn-success")
        self.assertNotContains(response, "Apply to device")
        self.assertContains(response, f'<a href="{current.get_absolute_url()}">current</a>', html=True)
        self.assertContains(response, f'<a href="{previous.get_absolute_url()}">previous</a>', html=True)
        self.assertContains(response, 'title="previous-checksum"')
        self.assertContains(response, ">previous-che</code>")
        self.assertContains(
            response,
            reverse("plugins:main:configurationbackup_restore", kwargs={"pk": previous.pk}),
        )
        self.assertNotContains(
            response,
            reverse("plugins:main:configurationbackup_restore", kwargs={"pk": current.pk}),
        )

    def test_restore_redirects_to_plugin_device_page(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="previous",
            config_text="hostname previous",
            source="runtime",
        )

        with patch.object(TaskExecutor, "restore_backup_to_device", return_value="ok") as restore:
            response = self.client.post(
                reverse("plugins:main:configurationbackup_restore", kwargs={"pk": backup.pk})
            )

        restore.assert_called_once_with(backup)
        self.assertRedirects(response, self.profile.get_absolute_url(), fetch_redirect_response=False)

    def test_configuration_diff_page_highlights_added_and_removed_lines(self):
        ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="before",
            config_text="hostname old\ninterface Ethernet0/0\n description old",
            source="runtime",
        )
        ConfigurationBackup.objects.create(
            device=self.device,
            version=2,
            version_name="after",
            config_text="hostname new\ninterface Ethernet0/0\n description new",
            source="runtime",
        )

        response = self.client.get(
            reverse("plugins:main:deviceplatformprofile_versions_diff", kwargs={"pk": self.profile.pk}),
            {"from": 1, "to": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "-hostname old")
        self.assertContains(response, "+hostname new")
        self.assertContains(response, "---")
        self.assertContains(response, "+++")

    def test_restore_yaml_configuration_generates_commands_and_creates_new_version_when_changed(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="selected",
            config_text=ConfigurationYamlService.dump_yaml(
                {
                    "schema_version": 1,
                    "device": {"id": self.device.pk, "name": self.device.name},
                    "platform": self.profile.platform,
                    "source": "runtime",
                    "saved_at": "2026-05-07T00:00:00+03:00",
                    "operations": [
                        {
                            "name": "hostname",
                            "operation_type": "custom",
                            "params": {"hostname": "selected-hostname"},
                        }
                    ],
                    "raw_commands": ["ip default-gateway 192.0.2.1"],
                }
            ),
            source="runtime",
            config_checksum="checksum",
        )
        session = self._mock_session("hostname selected-hostname")

        with TemporaryDirectory() as tmpdir:
            with (
                patch("main.application.tasks.connect_device_cli", return_value=(session, self.profile, {"checked": False})),
                patch.object(ConfigurationVCS, "repo_path", return_value=Path(tmpdir)),
                patch("main.infrastructure.vcs.subprocess.run"),
                patch("main.infrastructure.vcs.subprocess.check_output", return_value=b"abc123\n"),
            ):
                result = TaskExecutor.restore_backup_to_device(backup)

        session.send_config_set.assert_called_once_with([
            "hostname selected-hostname",
            "ip default-gateway 192.0.2.1",
            "write memory",
        ])
        self.assertIn("Configuration v1 sent to device", result)
        self.assertEqual(ConfigurationBackup.objects.filter(device=self.device).count(), 2)
        restored = ConfigurationBackup.objects.filter(device=self.device).order_by("-version").first()
        self.assertEqual(restored.source, "restore")
        self.assertTrue(ConfigurationYamlService.is_yaml_config(restored.config_text))

    def test_restore_yaml_configuration_does_not_create_new_version_when_unchanged(self):
        config_text = ConfigurationYamlService.running_config_to_yaml(
            self.device,
            "hostname selected-hostname",
            source="runtime",
        )
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="selected",
            config_text=config_text,
            source="runtime",
            config_checksum=ConfigurationYamlService.checksum(config_text),
        )
        session = self._mock_session("hostname selected-hostname")

        with patch("main.application.tasks.connect_device_cli", return_value=(session, self.profile, {"checked": False})):
            result = TaskExecutor.restore_backup_to_device(backup)

        session.send_config_set.assert_called_once_with([
            "hostname selected-hostname",
            "write memory",
        ])
        self.assertIn("Configuration v1 sent to device", result)
        self.assertIn("no new version created", result)
        self.assertEqual(ConfigurationBackup.objects.filter(device=self.device).count(), 1)

    def test_refresh_ignores_yaml_metadata_timestamps_when_comparing(self):
        payload = ConfigurationYamlService.running_config_to_payload(
            self.device,
            "hostname refresh-sw1",
            source="runtime",
        )
        payload["saved_at"] = "2026-05-07T00:00:00+03:00"
        payload["updated_at"] = "2026-05-08T00:00:00+03:00"
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="metadata-only",
            config_text=ConfigurationYamlService.dump_yaml(payload),
            source="runtime",
            config_checksum="old",
        )
        session = self._mock_session("hostname refresh-sw1")

        with patch("main.application.backups.connect_device_cli", return_value=(session, self.profile, {"checked": False})):
            result = ConfigurationService.refresh_device_config(self.device, compare_to=backup)

        self.assertFalse(result["changed"])
        self.assertEqual(result["backup"], backup)
        self.assertEqual(ConfigurationBackup.objects.filter(device=self.device).count(), 1)

    def test_refresh_ignores_device_last_configuration_change_comment(self):
        baseline_text = ConfigurationYamlService.running_config_to_yaml(
            self.device,
            "hostname refresh-sw1",
            source="runtime",
        )
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="without-device-timestamp",
            config_text=baseline_text,
            source="runtime",
            config_checksum="old",
        )
        running_config = """
Building configuration...
Current configuration : 1234 bytes
!
! Last configuration change at 22:57:02 UTC Fri May 8 2026 by admin
hostname refresh-sw1
!
end
"""
        session = self._mock_session(running_config)

        with patch("main.application.backups.connect_device_cli", return_value=(session, self.profile, {"checked": False})):
            result = ConfigurationService.refresh_device_config(self.device, compare_to=backup)

        self.assertFalse(result["changed"])
        self.assertEqual(result["backup"], backup)
        self.assertEqual(ConfigurationBackup.objects.filter(device=self.device).count(), 1)

    def test_running_config_yaml_ignores_device_timestamp_comments(self):
        yaml_text = ConfigurationYamlService.running_config_to_yaml(
            self.device,
            """
Building configuration...
!
! Last configuration change at 22:57:02 UTC Fri May 8 2026 by admin
! NVRAM config last updated at 22:58:02 UTC Fri May 8 2026 by admin
hostname refresh-sw1
!
end
""",
        )
        payload = ConfigurationYamlService.load_payload(yaml_text)

        serialized = ConfigurationYamlService.dump_yaml(payload)
        self.assertIn("refresh-sw1", serialized)
        self.assertNotIn("Last configuration change", serialized)
        self.assertNotIn("NVRAM config last updated", serialized)

    def test_raw_config_compare_ignores_device_timestamp_comments(self):
        first = "hostname refresh-sw1\nend"
        second = """
Building configuration...
!
! Last configuration change at 22:57:02 UTC Fri May 8 2026 by admin
hostname refresh-sw1
!
end
"""

        self.assertTrue(ConfigurationYamlService.configs_equivalent(first, second))

    def test_running_config_yaml_keeps_interface_raw_commands_in_section(self):
        raw_config = """
hostname Switch3
!
ip routing
!
interface FastEthernet0/5
 shutdown
!
interface Vlan100
 mac-address 000c.8564.5402
 ip address 38.189.96.100 255.255.224.0
 ip access-group Permit_Admin in
!
ip access-list extended Deny_Admin
 deny ip any 38.189.96.0 0.0.31.255
 permit icmp any host 38.189.96.101 echo-reply
!
line vty 0
 password switch3
 login
!
end
"""
        yaml_text = ConfigurationYamlService.running_config_to_yaml(self.device, raw_config)
        payload = ConfigurationYamlService.load_payload(yaml_text)

        self.assertEqual(payload["schema_version"], 2)
        self.assertNotIn("shutdown", payload["raw_commands"])
        section_map = {section["header"]: section for section in payload["sections"]}
        self.assertIn("interface FastEthernet0/5", section_map)
        self.assertFalse(section_map["interface FastEthernet0/5"]["raw_commands"])
        self.assertIn("ip access-list extended Deny_Admin", section_map)
        self.assertNotIn("deny ip any 38.189.96.0 0.0.31.255", payload["raw_commands"])
        self.assertIn("line vty 0", section_map)

        commands = ConfigurationYamlService.yaml_to_commands(yaml_text, self.profile)
        self.assertIn("interface FastEthernet0/5", commands)
        self.assertGreater(commands.index("shutdown"), commands.index("interface FastEthernet0/5"))
        self.assertIn("ip access-list extended Deny_Admin", commands)
        self.assertGreater(commands.index("deny ip any 38.189.96.0 0.0.31.255"), commands.index("ip access-list extended Deny_Admin"))
        self.assertIn("line vty 0", commands)
        self.assertGreater(commands.index("login"), commands.index("line vty 0"))

    def test_running_config_yaml_keeps_ipv6_tunnel_and_gatekeeper_context(self):
        raw_config = """
Building configuration...
Current configuration : 1556 bytes
!
hostname R7
!
ipv6 unicast-routing
ipv6 cef
!
interface Tunnel0
 no ip address
 ipv6 address FE80::7 link-local
 ipv6 address FD00:0:0:8::7/64
 ipv6 enable
 no ipv6 nd ra suppress
 tunnel source FastEthernet1/0
 tunnel mode ipv6ip
 tunnel destination 185.216.178.129
!
interface FastEthernet3/0
 no ip address
 shutdown
 duplex half
!
ipv6 route ::/0 FastEthernet2/0 FE80::4
!
gatekeeper
 shutdown
!
line con 0
 exec-timeout 0 0
 privilege level 15
 logging synchronous
 stopbits 1
!
end
"""
        yaml_text = ConfigurationYamlService.running_config_to_yaml(self.device, raw_config)
        payload = ConfigurationYamlService.load_payload(yaml_text)
        section_map = {section["header"]: section for section in payload["sections"]}

        self.assertNotIn("shutdown", payload["raw_commands"])
        self.assertIn("interface Tunnel0", section_map)
        self.assertIn("interface FastEthernet3/0", section_map)
        self.assertIn("gatekeeper", section_map)
        self.assertEqual(section_map["gatekeeper"]["raw_commands"], ["shutdown"])
        self.assertIn("line con 0", section_map)

        commands = ConfigurationYamlService.yaml_to_commands(yaml_text, self.profile)
        self.assertIn("interface FastEthernet3/0", commands)
        self.assertGreater(commands.index("shutdown"), commands.index("interface FastEthernet3/0"))
        self.assertIn("gatekeeper", commands)
        self.assertGreater(commands.index("shutdown", commands.index("gatekeeper")), commands.index("gatekeeper"))
        self.assertIn("ipv6 route ::/0 FastEthernet2/0 FE80::4", commands)

    def test_running_config_yaml_keeps_nat_router_sections_contextual(self):
        raw_config = """
Current configuration : 1104 bytes
!
hostname Router
!
no ip cef
no ipv6 cef
spanning-tree mode pvst
!
interface FastEthernet0/0
 ip address 167.177.5.249 255.255.255.248
 ip nat outside
 duplex auto
 speed auto
!
interface FastEthernet0/1
 ip address 69.20.59.1 255.255.255.0
 ip nat inside
 duplex auto
 speed auto
!
interface Vlan1
 no ip address
 shutdown
!
router rip
!
ip nat inside source static 69.20.59.2 202.141.23.115
ip route 0.0.0.0 0.0.0.0 167.177.5.250
!
line vty 0 4
 login
!
end
"""
        yaml_text = ConfigurationYamlService.running_config_to_yaml(self.device, raw_config)
        payload = ConfigurationYamlService.load_payload(yaml_text)
        section_map = {section["header"]: section for section in payload["sections"]}

        self.assertNotIn("login", payload["raw_commands"])
        self.assertNotIn("shutdown", payload["raw_commands"])
        self.assertIn("interface Vlan1", section_map)
        self.assertIn("router rip", section_map)
        self.assertIn("line vty 0 4", section_map)

        commands = ConfigurationYamlService.yaml_to_commands(yaml_text, self.profile)
        self.assertIn("interface Vlan1", commands)
        self.assertGreater(commands.index("shutdown"), commands.index("interface Vlan1"))
        self.assertIn("router rip", commands)
        self.assertIn("ip nat inside source static 69.20.59.2 202.141.23.115", commands)

    def test_scheduled_task_preview_includes_save_command(self):
        CommandTemplate.objects.create(
            name="hostname",
            vendor="cisco",
            platform="cisco_ios",
            operation_type=CommandTemplate.OP_CUSTOM,
            command_body="hostname {hostname}",
            is_active=True,
        )
        scheduled_task = ScheduledTask.objects.create(
            task_name="preview-save",
            task_type=ScheduledTask.TYPE_APPLY_SCENARIO,
            target_device=self.device,
            task=(
                "operations:\n"
                "  - name: hostname\n"
                "    operation_type: custom\n"
                "    params:\n"
                "      hostname: preview-hostname\n"
            ),
            schedule_time=timezone.now(),
        )

        commands = TaskExecutor.preview_commands(scheduled_task)

        self.assertEqual(commands[-1], "write memory")
        self.assertIn("hostname preview-hostname", commands)

    def test_scheduled_task_list_truncates_yaml_and_links_to_profile(self):
        task_yaml = (
            "operations:\n"
            "  - name: hostname\n"
            "    operation_type: custom\n"
            "    params:\n"
            "      hostname: very-long-hostname-for-table-preview\n"
            "raw_commands:\n"
            "  - interface Ethernet0/0\n"
            "  - description very long description for the scheduled task table\n"
        )
        scheduled_task = ScheduledTask.objects.create(
            task_name="long-yaml-task",
            task_type=ScheduledTask.TYPE_APPLY_SCENARIO,
            target_device=self.device,
            task=task_yaml,
            schedule_time=timezone.now(),
        )

        response = self.client.get(reverse("plugins:main:scheduledtask_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, scheduled_task.get_absolute_url())
        self.assertContains(response, ">long-yaml-task</a>")
        self.assertContains(response, '<code title="operations:')
        self.assertContains(response, "...")
        self.assertNotContains(response, "description very long description for the scheduled task table</code>")

    def test_scheduled_task_profile_shows_full_task_information(self):
        task_yaml = (
            "operations:\n"
            "  - name: hostname\n"
            "    operation_type: custom\n"
            "    params:\n"
            "      hostname: profile-hostname\n"
        )
        scheduled_task = ScheduledTask.objects.create(
            task_name="profile-yaml-task",
            task_type=ScheduledTask.TYPE_APPLY_SCENARIO,
            target_device=self.device,
            task=task_yaml,
            schedule_time=timezone.now(),
            run_every_seconds=300,
            max_retries=2,
            retry_count=1,
            status=ScheduledTask.STATUS_FAILED,
            result_message="last run failed",
        )

        response = self.client.get(scheduled_task.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Task profile")
        self.assertContains(response, "profile-yaml-task")
        self.assertContains(response, "Apply scenario")
        self.assertContains(response, self.device.name)
        self.assertContains(response, "Failed")
        self.assertContains(response, "300")
        self.assertContains(response, "2")
        self.assertContains(response, "1")
        self.assertContains(response, "last run failed")
        self.assertContains(response, '<div class="mb-0 text-body" style="white-space: pre-wrap;">last run failed</div>')
        self.assertNotContains(response, "<pre class=\"mb-0 text-wrap\"><code>last run failed</code></pre>")
        self.assertContains(response, "Task YAML")
        self.assertContains(response, '<pre class="mb-0 yaml-code-block"><code data-yaml-highlight>operations:')
        self.assertContains(response, "hostname: profile-hostname")
        self.assertContains(response, "Preview commands")
        self.assertContains(response, "Create version")
        self.assertContains(response, "Run")
        self.assertContains(response, 'type="checkbox" name="confirm_create_version"')

    def test_generated_version_names_are_unique_for_same_base_name(self):
        fixed_dt = datetime(2026, 5, 5, 20, 45, tzinfo=timezone.get_current_timezone())
        base_name = ConfigurationVCS.build_version_name(self.device, fixed_dt)
        ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name=base_name,
            config_text="hostname refresh-sw1",
        )
        ConfigurationBackup.objects.create(
            device=self.device,
            version=2,
            version_name=f"{base_name}_1",
            config_text="hostname refresh-sw1",
        )

        self.assertEqual(
            ConfigurationVCS.build_unique_version_name(self.device, fixed_dt),
            f"{base_name}_2",
        )

    def test_generated_version_name_suffix_respects_max_length(self):
        max_length = ConfigurationBackup._meta.get_field("version_name").max_length
        ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name="v" * max_length,
            config_text="hostname long-device",
        )

        with patch.object(ConfigurationVCS, "build_version_name", return_value="v" * (max_length + 20)):
            version_name = ConfigurationVCS.build_unique_version_name(self.device)

        self.assertLessEqual(len(version_name), max_length)
        self.assertTrue(version_name.endswith("_1"))

    def test_write_backup_uses_unique_version_name(self):
        fixed_dt = datetime(2026, 5, 5, 20, 45, tzinfo=timezone.get_current_timezone())
        base_name = ConfigurationVCS.build_version_name(self.device, fixed_dt)
        ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            version_name=base_name,
            config_text="hostname refresh-sw1",
        )

        with TemporaryDirectory() as tmpdir:
            with (
                patch.object(ConfigurationVCS, "repo_path", return_value=Path(tmpdir)),
                patch("main.infrastructure.vcs.timezone.now", return_value=fixed_dt),
                patch("main.infrastructure.vcs.subprocess.run"),
                patch("main.infrastructure.vcs.subprocess.check_output", return_value=b"abc123\n"),
            ):
                backup = ConfigurationVCS.write_backup(self.device, "hostname refresh-sw1")

        self.assertEqual(backup.version_name, f"{base_name}_1")
        self.assertTrue(ConfigurationYamlService.is_yaml_config(backup.config_text))
