from django.test import SimpleTestCase

from main.security import redact_secrets


class RedactionTests(SimpleTestCase):
    def test_redacts_cisco_secrets(self):
        config = """
username admin password 0 superpass
enable secret 5 hash123
snmp-server community public RO
""".strip()

        redacted = redact_secrets(config)

        self.assertNotIn("superpass", redacted)
        self.assertNotIn("hash123", redacted)
        self.assertNotIn("public", redacted)
        self.assertIn("<REDACTED>", redacted)
