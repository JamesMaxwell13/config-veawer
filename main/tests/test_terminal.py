from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import TestCase, override_settings
from django.urls import reverse
from users.models import User

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

    def test_device_page_has_terminal_button(self):
        response = self.client.get(self.profile.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_terminal", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, "Терминал")

    def test_netbox_device_page_has_terminal_button(self):
        response = self.client.get(self.device.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("plugins:main:deviceplatformprofile_terminal", kwargs={"pk": self.profile.pk}),
        )
        self.assertContains(response, "Терминал")

    def test_plugin_device_list_has_netbox_device_and_terminal_links(self):
        response = self.client.get(reverse("plugins:main:deviceplatformprofile_list"))

        self.assertEqual(response.status_code, 200)
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
        self.assertContains(response, "SSH configure terminal")
        self.assertContains(
            response,
            f"/ws/plugins/config-weaver/devices/{self.profile.pk}/terminal/",
        )
