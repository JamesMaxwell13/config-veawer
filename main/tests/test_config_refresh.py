from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import TestCase, override_settings
from django.urls import reverse
from users.models import User

from main.application.backups import ConfigurationService
from main.domain.security import redact_secrets
from main.infrastructure.vcs import ConfigurationVCS
from main.models import ConfigurationBackup, DeviceCredential, DevicePlatformProfile


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
        self.assertContains(response, "Проверить конфиг")

    def test_device_page_has_get_config_button(self):
        response = self.client.get(self.profile.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_refresh_config", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, "Получить конфиг")
