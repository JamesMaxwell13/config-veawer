from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import TestCase, override_settings
from django.urls import reverse
from users.models import User

from main.application.terminal import DeviceTerminalService
from main.infrastructure.vcs import ConfigurationVCS
from main.models import DeviceCredential, DevicePlatformProfile


def create_device(name="terminal-sw1"):
    manufacturer = Manufacturer.objects.create(name=f"{name} manufacturer", slug=f"{name}-manufacturer")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model=f"{name} type", slug=f"{name}-type")
    role = DeviceRole.objects.create(name=f"{name} role", slug=f"{name}-role")
    site = Site.objects.create(name=f"{name} site", slug=f"{name}-site")
    return Device.objects.create(site=site, device_type=device_type, role=role, name=name)


@override_settings(PLUGINS_CONFIG={"main": {"secret_key": "test-secret-key"}})
class DeviceTerminalViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.device = create_device()
        self.credential = DeviceCredential.objects.create(
            name="terminal-cred",
            username="admin",
            password="password",
        )
        self.profile = DevicePlatformProfile.objects.create(
            device=self.device,
            credential=self.credential,
            vendor=DevicePlatformProfile.VENDOR_CISCO,
            platform=DevicePlatformProfile.PLATFORM_CISCO_IOS,
            management_ip="192.0.2.10",
            enabled=True,
        )
        self.client.force_login(self.user)

    def test_profile_page_renders_config_weaver_profile(self):
        response = self.client.get(self.profile.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Доступные команды")
        self.assertContains(response, "Открыть команды")
        self.assertContains(response, reverse("plugins:main:commandtemplate_list"))
        self.assertContains(response, "vendor=cisco")
        self.assertContains(response, "platform=cisco_ios")
        self.assertNotContains(response, "CLI устройства")
        self.assertNotContains(response, "device-cli-form")

    def test_netbox_device_page_has_configurations_button(self):
        response = self.client.get(self.device.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            self.profile.get_absolute_url(),
        )
        self.assertContains(response, 'class="btn btn-secondary"')
        self.assertContains(response, "Профиль Config Weaver")
        self.assertNotContains(
            response,
            reverse("plugins:main:deviceplatformprofile_terminal", kwargs={"pk": self.profile.pk}),
        )

    def test_plugin_device_list_has_netbox_device_and_terminal_links(self):
        response = self.client.get(reverse("plugins:main:deviceplatformprofile_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.profile.get_absolute_url())
        self.assertContains(response, self.device.get_absolute_url())
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_terminal", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, "Устройство NetBox")
        self.assertContains(response, "Профиль Config Weaver")

    def test_terminal_page_renders_websocket_path(self):
        response = self.client.get(
            reverse("plugins:main:deviceplatformprofile_terminal", kwargs={"pk": self.profile.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "SSH configure terminal")
        self.assertContains(response, 'id="terminal-status"')
        self.assertContains(
            response,
            f"/ws/plugins/config-weaver/devices/{self.profile.pk}/terminal/",
        )
        self.assertContains(response, f'data-device-url="{self.profile.get_absolute_url()}"')
        self.assertContains(response, "main/device_terminal.js")

    def test_terminal_close_saves_configuration_before_backup(self):
        transport = MagicMock()
        transport.read_command.return_value = "hostname terminal-sw1"
        service = DeviceTerminalService(self.profile, self.user, transport=transport)
        service.closed = False

        with TemporaryDirectory() as tmpdir:
            with (
                patch.object(ConfigurationVCS, "repo_path", return_value=Path(tmpdir)),
                patch("main.infrastructure.vcs.subprocess.run"),
                patch("main.infrastructure.vcs.subprocess.check_output", return_value=b"abc123\n"),
            ):
                service.close()

        transport.send_line.assert_any_call("end")
        transport.send_line.assert_any_call("write memory")
        sent_commands = [call.args[0] for call in transport.send_line.call_args_list]
        self.assertLess(sent_commands.index("end"), sent_commands.index("write memory"))
        transport.read_command.assert_called_once_with("show running-config")
