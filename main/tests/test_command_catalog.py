from django.test import SimpleTestCase, TestCase
from django.core.cache import cache
from django.core.management import call_command

from main.domain.command_catalog import CommandCatalog
from main.domain.configuration import CommandGenerator, ConfigurationValidator
from main.models import CommandTemplate, DevicePlatformProfile


class CommandCatalogLoaderTests(TestCase):
    def tearDown(self):
        cache.delete("cw:templates:active")

    def test_loads_vendor_yaml_templates(self):
        templates = CommandCatalog.file_templates()
        keys = {(template.vendor, template.platform, template.name) for template in templates}

        self.assertIn(("cisco", "cisco_ios", "interface_l3"), keys)
        self.assertIn(("dlink", "dlink_ds", "vlan_create"), keys)

    def test_database_template_overrides_catalog_template(self):
        template = CommandTemplate.objects.create(
            name="hostname",
            vendor="cisco",
            platform="cisco_ios",
            operation_type=CommandTemplate.OP_CUSTOM,
            command_body="hostname db-{hostname}",
            is_active=True,
        )

        templates = CommandCatalog.merge_with_database([template])
        selected = [
            item
            for item in templates
            if item.vendor == "cisco"
            and item.platform == "cisco_ios"
            and item.operation_type == CommandTemplate.OP_CUSTOM
            and item.name == "hostname"
        ]

        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0], template)

    def test_command_template_save_invalidates_active_template_cache(self):
        cache.set("cw:templates:active", ["stale"], timeout=120)

        CommandTemplate.objects.create(
            name="custom",
            vendor="cisco",
            platform="cisco_ios",
            operation_type=CommandTemplate.OP_CUSTOM,
            command_body="hostname {hostname}",
            is_active=True,
        )

        self.assertIsNone(cache.get("cw:templates:active"))

    def test_sync_command_templates_creates_database_templates(self):
        call_command("sync_command_templates")

        self.assertTrue(
            CommandTemplate.objects.filter(
                vendor="cisco",
                platform="cisco_ios",
                name="nat_overload",
            ).exists()
        )
        self.assertTrue(
            CommandTemplate.objects.filter(
                vendor="dlink",
                platform="dlink_ds",
                name="access_vlan",
            ).exists()
        )


class CommandGeneratorCatalogTests(SimpleTestCase):
    def setUp(self):
        self.profile = DevicePlatformProfile(vendor="cisco", platform="cisco_ios")
        self.templates = CommandCatalog.file_templates()

    def test_generates_named_multiline_catalog_operation(self):
        plan = {
            "operations": [
                {
                    "name": "interface_l3",
                    "params": {
                        "interface": "GigabitEthernet0/1",
                        "ip": "10.0.0.1",
                        "mask": "255.255.255.0",
                    },
                }
            ]
        }

        commands = CommandGenerator.generate_commands(plan, self.templates, self.profile)

        self.assertEqual(
            commands,
            [
                "interface GigabitEthernet0/1",
                "no switchport",
                "ip address 10.0.0.1 255.255.255.0",
                "no shutdown",
            ],
        )

    def test_adds_raw_commands(self):
        plan = {
            "operations": [
                {
                    "raw_commands": "interface Loopback10\n description raw",
                }
            ],
            "raw_commands": ["do show version"],
        }

        commands = CommandGenerator.generate_commands(plan, self.templates, self.profile)

        self.assertEqual(commands, ["interface Loopback10", "description raw", "do show version"])

    def test_legacy_interfaces_still_work(self):
        plan = {
            "interfaces": [
                {
                    "name": "GigabitEthernet0/2",
                    "description": "legacy",
                    "ip": "10.0.2.1",
                    "mask": "255.255.255.0",
                }
            ]
        }

        commands = CommandGenerator.generate_commands(plan, self.templates, self.profile)

        self.assertIn("interface GigabitEthernet0/2", commands)
        self.assertIn("description legacy", commands)
        self.assertIn("ip address 10.0.2.1 255.255.255.0", commands)

    def test_validator_blocks_dangerous_raw_command(self):
        valid, errors = ConfigurationValidator.validate_commands(["reload"])

        self.assertFalse(valid)
        self.assertTrue(errors)
