from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from users.models import User

from main.application.backups import ConfigurationService
from main.application.configuration_yaml import ConfigurationYamlService
from main.application.tasks import TaskExecutor
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
            config_checksum="checksum",
        )

        response = self.client.get(backup.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("plugins:main:configurationbackup_refresh", kwargs={"pk": backup.pk}),
        )
        self.assertContains(response, "Проверить конфигурацию")

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
        self.assertNotContains(response, "Просмотреть YAML")
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
        self.assertNotContains(response, "Открыть")
        self.assertContains(response, 'title="abcdef1234567890"')
        self.assertContains(response, ">abcdef123456</code>")
        self.assertContains(response, 'title="1234567890abcdef"')
        self.assertContains(response, ">1234567890ab</code>")

    def test_profile_page_renders_config_weaver_profile(self):
        response = self.client.get(self.profile.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Доступные команды")
        self.assertNotContains(response, "CLI устройства")
        self.assertContains(response, "Последние конфигурации")

    def test_device_configurations_page_has_get_config_button(self):
        response = self.client.get(reverse("dcim:device_configurations", kwargs={"pk": self.device.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_refresh_config", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, "Получить конфигурацию")

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
        self.assertContains(response, "Текущая конфигурация")
        self.assertContains(response, "v2")
        self.assertContains(response, "current")
        self.assertContains(response, "Предыдущие конфигурации")
        self.assertContains(response, "previous")
        self.assertContains(
            response,
            reverse("plugins:main:configurationbackup_restore", kwargs={"pk": previous.pk}),
        )
        self.assertContains(response, "Отправить на устройство")
        self.assertNotContains(response, "CLI устройства")
        self.assertNotContains(response, "Ближайшие задачи планировщика")

    def test_configuration_versions_page_marks_current_and_can_send_previous(self):
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

        response = self.client.get(reverse("plugins:main:configuration_versions", kwargs={"device_id": self.device.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текущая")
        self.assertContains(response, "Отправить на устройство", count=1)
        self.assertContains(
            response,
            reverse("plugins:main:configurationbackup_restore", kwargs={"pk": previous.pk}),
        )
        self.assertNotContains(
            response,
            reverse("plugins:main:configurationbackup_restore", kwargs={"pk": current.pk}),
        )

    def test_restore_yaml_configuration_generates_commands_and_creates_new_version(self):
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
        self.assertIn("Конфигурация v1 отправлена на устройство", result)
        self.assertEqual(ConfigurationBackup.objects.filter(device=self.device).count(), 2)
        restored = ConfigurationBackup.objects.filter(device=self.device).order_by("-version").first()
        self.assertEqual(restored.source, "restore")
        self.assertTrue(ConfigurationYamlService.is_yaml_config(restored.config_text))

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
