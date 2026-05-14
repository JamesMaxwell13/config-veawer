from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from users.models import User

from main.models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    ScheduledTask,
)


def create_device(name="bulk-sw1"):
    manufacturer = Manufacturer.objects.create(name=f"{name} manufacturer", slug=f"{name}-manufacturer")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model=f"{name} type", slug=f"{name}-type")
    role = DeviceRole.objects.create(name=f"{name} role", slug=f"{name}-role")
    site = Site.objects.create(name=f"{name} site", slug=f"{name}-site")
    return Device.objects.create(site=site, device_type=device_type, role=role, name=name)


@override_settings(PLUGINS_CONFIG={"main": {"secret_key": "test-secret-key"}})
class BulkActionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_login(self.user)
        self.device = create_device()
        self.credential = DeviceCredential.objects.create(
            name="bulk-cred",
            username="admin",
            password="password",
        )
        self.profile = DevicePlatformProfile.objects.create(
            device=self.device,
            credential=self.credential,
            vendor=DevicePlatformProfile.VENDOR_CISCO,
            platform=DevicePlatformProfile.PLATFORM_CISCO_IOS,
            management_ip="192.0.2.30",
            enabled=True,
        )
        self.template = CommandTemplate.objects.create(
            name="bulk-template",
            vendor="cisco",
            platform="cisco_ios",
            operation_type=CommandTemplate.OP_CUSTOM,
            command_body="hostname {name}",
        )
        self.backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text="hostname bulk-sw1",
            source="runtime",
        )
        self.task = ScheduledTask.objects.create(
            task_name="bulk-task",
            task_type=ScheduledTask.TYPE_BACKUP,
            target_device=self.device,
            task="",
            schedule_time=timezone.now(),
            status=ScheduledTask.STATUS_PENDING,
        )

    def test_standard_bulk_urls_reverse(self):
        for viewname in (
            "devicecredential_bulk_edit",
            "devicecredential_bulk_delete",
            "deviceplatformprofile_bulk_edit",
            "deviceplatformprofile_bulk_delete",
            "commandtemplate_bulk_edit",
            "commandtemplate_bulk_delete",
            "configurationbackup_bulk_edit",
            "configurationbackup_bulk_delete",
            "scheduledtask_bulk_edit",
            "scheduledtask_bulk_delete",
        ):
            self.assertTrue(reverse(f"plugins:main:{viewname}"))

    def test_list_pages_render_standard_bulk_action_urls(self):
        for list_view, bulk_edit_view, bulk_delete_view in (
            ("devicecredential_list", "devicecredential_bulk_edit", "devicecredential_bulk_delete"),
            ("deviceplatformprofile_list", "deviceplatformprofile_bulk_edit", "deviceplatformprofile_bulk_delete"),
            ("commandtemplate_list", "commandtemplate_bulk_edit", "commandtemplate_bulk_delete"),
            ("configurationbackup_list", "configurationbackup_bulk_edit", "configurationbackup_bulk_delete"),
            ("scheduledtask_list", "scheduledtask_bulk_edit", "scheduledtask_bulk_delete"),
        ):
            response = self.client.get(reverse(f"plugins:main:{list_view}"))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, reverse(f"plugins:main:{bulk_edit_view}"))
            self.assertContains(response, reverse(f"plugins:main:{bulk_delete_view}"))

    def test_bulk_edit_updates_selected_object(self):
        response = self.client.post(
            reverse("plugins:main:scheduledtask_bulk_edit"),
            {
                "pk": [self.task.pk],
                "status": ScheduledTask.STATUS_FAILED,
                "_apply": "Apply",
                "return_url": reverse("plugins:main:scheduledtask_list"),
            },
        )

        self.assertRedirects(response, reverse("plugins:main:scheduledtask_list"))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, ScheduledTask.STATUS_FAILED)

    def test_bulk_delete_deletes_selected_object(self):
        response = self.client.post(
            reverse("plugins:main:commandtemplate_bulk_delete"),
            {
                "pk": [self.template.pk],
                "confirm": True,
                "_confirm": "Confirm",
                "return_url": reverse("plugins:main:commandtemplate_list"),
            },
        )

        self.assertRedirects(response, reverse("plugins:main:commandtemplate_list"))
        self.assertFalse(CommandTemplate.objects.filter(pk=self.template.pk).exists())

    def test_command_template_list_has_compact_columns(self):
        response = self.client.get(reverse("plugins:main:commandtemplate_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">Name</a>", html=False)
        self.assertContains(response, ">Vendor</a>", html=False)
        self.assertContains(response, ">Operation type</a>", html=False)
        self.assertContains(response, ">Last updated</a>", html=False)
        self.assertNotContains(response, ">Platform</a>", html=False)
        self.assertNotContains(response, ">Revision</a>", html=False)
        self.assertNotContains(response, ">Created</a>", html=False)
        self.assertContains(response, self.template.get_absolute_url())

    def test_command_template_detail_renders_profile_sections(self):
        self.template.bound_entity_type = CommandTemplate.ENTITY_INTERFACE
        self.template.bound_parameter = "description"
        self.template.bound_direction = CommandTemplate.DIRECTION_BOTH
        self.template.binding_priority = 50
        self.template.revision = 3
        self.template.command_body = "interface {interface}\ndescription {description}"
        self.template.save()

        response = self.client.get(self.template.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Command template profile")
        self.assertContains(response, "Operation type")
        self.assertContains(response, "Custom")
        self.assertContains(response, "Bound entity")
        self.assertContains(response, "Interface")
        self.assertContains(response, "interface.description")
        self.assertContains(response, "Binding priority")
        self.assertContains(response, "50")
        self.assertNotContains(response, "<dt class=\"col-sm-3\">Command body</dt>", html=True)
        self.assertContains(response, '<pre class="mb-0 yaml-code-block cw-command-body"><code>', html=False)
        self.assertContains(response, "interface {interface}")
        self.assertContains(response, reverse("plugins:main:commandtemplate_preview", kwargs={"pk": self.template.pk}))
