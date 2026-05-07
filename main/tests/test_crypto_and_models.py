from django.test import TestCase, override_settings
from django.urls import reverse
from users.models import User

from main.infrastructure.crypto import decrypt_value, encrypt_value, is_encrypted
from main.models import DeviceCredential
from main.presentation.forms import DeviceCredentialForm


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

    def test_device_credential_form_keeps_existing_secrets_when_editing(self):
        cred = DeviceCredential.objects.create(
            name="cred1",
            username="admin",
            password="plain-pass",
            enable_secret="plain-enable",
            ssh_port=22,
            timeout=10,
            use_enable=True,
            is_active=True,
        )

        form = DeviceCredentialForm(
            data={
                "name": "cred1-renamed",
                "auth_method": DeviceCredential.AUTH_PASSWORD,
                "username": "admin",
                "password": "",
                "enable_secret": "",
                "ssh_port": 22,
                "timeout": 10,
                "use_enable": "on",
                "is_active": "on",
            },
            instance=cred,
        )

        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.assertEqual(form.cleaned_data["password"], cred.password)
        self.assertEqual(form.cleaned_data["enable_secret"], cred.enable_secret)

    def test_reveal_credential_requires_netbox_username_and_password(self):
        user = User.objects.create_superuser(username="admin", password="netbox-pass")
        cred = DeviceCredential.objects.create(
            name="cred1",
            username="device-admin",
            password="plain-pass",
            enable_secret="plain-enable",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("plugins:main:devicecredential_reveal", kwargs={"pk": cred.pk}),
            {
                "account_username": "admin",
                "account_password": "netbox-pass",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "plain-pass")
        self.assertContains(response, "plain-enable")

    def test_reveal_credential_rejects_wrong_netbox_username(self):
        user = User.objects.create_superuser(username="admin", password="netbox-pass")
        cred = DeviceCredential.objects.create(
            name="cred1",
            username="device-admin",
            password="plain-pass",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("plugins:main:devicecredential_reveal", kwargs={"pk": cred.pk}),
            {
                "account_username": "other",
                "account_password": "netbox-pass",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неверный логин учетной записи NetBox.")
        self.assertNotContains(response, "plain-pass")

    def test_reveal_credential_rejects_wrong_netbox_password(self):
        user = User.objects.create_superuser(username="admin", password="netbox-pass")
        cred = DeviceCredential.objects.create(
            name="cred1",
            username="device-admin",
            password="plain-pass",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("plugins:main:devicecredential_reveal", kwargs={"pk": cred.pk}),
            {
                "account_username": "admin",
                "account_password": "wrong",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Неверный пароль учетной записи NetBox.")
        self.assertNotContains(response, "plain-pass")
