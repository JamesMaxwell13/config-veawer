from django.test import TestCase, override_settings

from main.crypto import decrypt_value, encrypt_value, is_encrypted
from main.models import DeviceCredential


@override_settings(PLUGINS_CONFIG={"main": {"secret_key": "test-secret-key"}})
class CryptoAndModelTests(TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        encrypted = encrypt_value("my-password")
        self.assertTrue(is_encrypted(encrypted))
        self.assertEqual(decrypt_value(encrypted), "my-password")

    def test_device_credential_stores_encrypted_values(self):
        cred = DeviceCredential.objects.create(
            name="cred1",
            username="admin",
            password="plain-pass",
            enable_secret="plain-enable",
            ssh_port=22,
            timeout=10,
            use_enable=True,
        )
        cred.refresh_from_db()

        self.assertNotEqual(cred.password, "plain-pass")
        self.assertNotEqual(cred.enable_secret, "plain-enable")
        self.assertTrue(is_encrypted(cred.password))
        self.assertTrue(is_encrypted(cred.enable_secret))
        self.assertEqual(cred.password_plain, "plain-pass")
        self.assertEqual(cred.enable_secret_plain, "plain-enable")
