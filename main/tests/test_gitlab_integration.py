from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, Rack, Site
from django.test import TestCase, override_settings
from django.urls import reverse
from users.models import User

from main.application.gitlab import GitLabIntegrationService
from main.infrastructure.crypto import is_encrypted
from main.infrastructure.gitlab import (
    GitLabClient,
    GitLabFileMetadata,
    GitLabNotFoundError,
    GitLabPathBuilder,
)
from main.models import (
    ConfigurationBackup,
    GitLabConfigMapping,
    GitLabIntegration,
    GitLabSyncLog,
    ScheduledTask,
)
from main.navigation import menu_items
from main.presentation import forms

WEBHOOK_URL = "/api/plugins/config-weaver/gitlab/webhook/"


def create_device(name="sw-core-01", with_site=True, with_location=True, with_rack=True):
    manufacturer = Manufacturer.objects.create(name=f"{name} Manufacturer", slug=f"{name}-manufacturer")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model=f"{name} type", slug=f"{name}-type")
    role = DeviceRole.objects.create(name=f"{name} Role", slug=f"{name}-role")
    site = Site.objects.create(name="Main Campus", slug="main-campus") if with_site else None
    location = None
    rack = None
    if site and with_location:
        location = Location.objects.create(name="Building A Floor 2", slug="building-a-floor-2", site=site)
    if site and location and with_rack:
        rack = Rack.objects.create(name="Rack 12", site=site, location=location)
    return Device.objects.create(
        site=site,
        location=location,
        rack=rack,
        device_type=device_type,
        role=role,
        name=name,
    )


@override_settings(PLUGINS_CONFIG={"main": {"secret_key": "test-secret-key"}})
class GitLabPathBuilderTests(TestCase):
    def test_builds_default_netbox_location_path(self):
        device = create_device()

        self.assertEqual(
            GitLabPathBuilder.build(device),
            "configs/main-campus/building-a-floor-2/rack-12/sw-core-01.yaml",
        )

    def test_fallbacks_for_missing_site_location_and_rack(self):
        device = create_device(with_location=False, with_rack=False)
        device.site = None

        self.assertEqual(
            GitLabPathBuilder.build(device),
            "configs/no-site/no-location/no-rack/sw-core-01.yaml",
        )

    def test_normalizes_unsafe_segments_and_blocks_traversal(self):
        device = create_device(name="../SW Core 01!!")

        self.assertEqual(
            GitLabPathBuilder.build(device),
            "configs/main-campus/building-a-floor-2/rack-12/sw-core-01.yaml",
        )

    def test_custom_pattern_uses_placeholders(self):
        device = create_device()

        self.assertEqual(
            GitLabPathBuilder.build(
                device,
                root_path="desired configs",
                pattern="{root_path}/{role_slug}/{manufacturer}/{device_id}/{device_name}.yaml",
            ),
            f"desired-configs/sw-core-01-role/sw-core-01-manufacturer/{device.pk}/sw-core-01.yaml",
        )


@override_settings(PLUGINS_CONFIG={"main": {"secret_key": "test-secret-key"}})
class GitLabIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_login(self.user)
        self.device = create_device()
        self.integration = GitLabIntegration.objects.create(
            name="prod",
            gitlab_url="https://gitlab.example.com",
            project_id="network/configs",
            branch="main",
            access_token="token",
            webhook_secret="secret",
        )

    def test_integration_stores_secrets_encrypted(self):
        self.integration.refresh_from_db()

        self.assertTrue(is_encrypted(self.integration.access_token))
        self.assertTrue(is_encrypted(self.integration.webhook_secret))
        self.assertEqual(self.integration.access_token_plain, "token")
        self.assertEqual(self.integration.webhook_secret_plain, "secret")

    def test_push_backup_creates_gitlab_file_when_missing(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text="interfaces:\n- name: gi0/1\n",
            source="manual",
        )
        gitlab = MagicMock()
        gitlab.get_file_metadata.side_effect = [
            GitLabNotFoundError("not found", 404),
            GitLabFileMetadata(file_path="x", last_commit_id="commit-1"),
        ]
        gitlab.create_file.return_value = {"commit_id": "commit-1"}

        with patch.object(GitLabIntegrationService, "client_for", return_value=gitlab):
            results = GitLabIntegrationService.push_backup_to_gitlab(backup, integration=self.integration)

        self.assertEqual(results[0].status, "success")
        gitlab.create_file.assert_called_once()
        mapping = GitLabConfigMapping.objects.get(integration=self.integration, device=self.device)
        self.assertEqual(mapping.last_gitlab_commit_sha, "commit-1")

    def test_push_to_gitlab_populates_empty_repository_with_latest_backups(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text="interfaces:\n- name: gi0/1\n",
            source="manual",
        )
        gitlab = MagicMock()
        gitlab.get_file_metadata.side_effect = [
            GitLabNotFoundError("not found", 404),
            GitLabFileMetadata(file_path="x", last_commit_id="commit-1"),
        ]
        gitlab.create_file.return_value = {"commit_id": "commit-1"}

        with patch.object(GitLabIntegrationService, "client_for", return_value=gitlab):
            results = GitLabIntegrationService.push_to_gitlab(self.integration)

        self.assertEqual(results[0].status, "success")
        gitlab.create_file.assert_called_once()
        self.assertEqual(gitlab.create_file.call_args.args[3], backup.config_text)

    def test_push_backup_force_updates_when_gitlab_file_changed(self):
        backup = ConfigurationBackup.objects.create(
            device=self.device,
            version=1,
            config_text="interfaces:\n- name: gi0/1\n",
            source="manual",
        )
        mapping = GitLabConfigMapping.objects.create(
            integration=self.integration,
            device=self.device,
            file_path=GitLabIntegrationService.build_file_path(self.integration, self.device),
            last_gitlab_commit_sha="old",
        )
        gitlab = MagicMock()
        gitlab.get_file_metadata.side_effect = [
            GitLabFileMetadata(mapping.file_path, "new"),
            GitLabFileMetadata(mapping.file_path, "commit-2"),
        ]
        gitlab.update_file.return_value = {"commit_id": "commit-2"}

        with patch.object(GitLabIntegrationService, "client_for", return_value=gitlab):
            results = GitLabIntegrationService.push_backup_to_gitlab(backup, integration=self.integration)

        self.assertEqual(results[0].status, "success")
        self.assertEqual(results[0].message, "Configuration force-pushed to GitLab.")
        gitlab.update_file.assert_called_once_with(
            self.integration.project_id,
            mapping.file_path,
            self.integration.branch,
            backup.config_text,
            f"Update config for {backup.device.name} from NetBox Config Weaver",
            last_commit_id="new",
        )
        mapping.refresh_from_db()
        self.assertEqual(mapping.last_gitlab_commit_sha, "commit-2")
        self.assertFalse(GitLabSyncLog.objects.filter(status=GitLabSyncLog.STATUS_CONFLICT).exists())

    def test_webhook_rejects_invalid_secret(self):
        response = self.client.post(
            WEBHOOK_URL,
            {"project": {"path_with_namespace": "network/configs"}, "ref": "refs/heads/main"},
            content_type="application/json",
            HTTP_X_GITLAB_TOKEN="wrong",
            HTTP_X_GITLAB_EVENT="Push Hook",
        )

        self.assertEqual(response.status_code, 403)

    def test_webhook_imports_changed_yaml_and_queues_auto_apply(self):
        self.integration.auto_apply = True
        self.integration.save()
        file_path = GitLabIntegrationService.build_file_path(self.integration, self.device)
        gitlab = MagicMock()
        gitlab.get_raw_file.return_value = "interfaces:\n- name: gi0/1\n"
        payload = {
            "project": {"path_with_namespace": "network/configs"},
            "ref": "refs/heads/main",
            "checkout_sha": "abc123",
            "commits": [{"added": [], "modified": [file_path], "removed": []}],
        }

        with patch.object(GitLabIntegrationService, "client_for", return_value=gitlab):
            response = self.client.post(
                WEBHOOK_URL,
                payload,
                content_type="application/json",
                HTTP_X_GITLAB_TOKEN="secret",
                HTTP_X_GITLAB_EVENT="Push Hook",
            )

        self.assertEqual(response.status_code, 200, response.content.decode())
        backup = ConfigurationBackup.objects.get(device=self.device, source="gitlab")
        self.assertEqual(backup.config_text, "interfaces:\n- name: gi0/1\n")
        mapping = GitLabConfigMapping.objects.get(integration=self.integration, device=self.device)
        self.assertEqual(mapping.last_gitlab_commit_sha, "abc123")
        self.assertEqual(ScheduledTask.objects.filter(target_device=self.device).count(), 1)

    def test_webhook_ignores_other_branch(self):
        payload = {
            "project": {"path_with_namespace": "network/configs"},
            "ref": "refs/heads/dev",
            "checkout_sha": "abc123",
            "commits": [{"modified": [GitLabIntegrationService.build_file_path(self.integration, self.device)]}],
        }

        response = self.client.post(
            WEBHOOK_URL,
            payload,
            content_type="application/json",
            HTTP_X_GITLAB_TOKEN="secret",
            HTTP_X_GITLAB_EVENT="Push Hook",
        )

        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertFalse(ConfigurationBackup.objects.filter(source="gitlab").exists())

    def test_plugin_menu_hides_gitlab_subpages_and_api_docs(self):
        links = {item.link for item in menu_items}

        self.assertIn("plugins:main:gitlabintegration_list", links)
        self.assertNotIn("plugins:main:gitlabconfigmapping_list", links)
        self.assertNotIn("plugins:main:gitlabsynclog_list", links)
        self.assertNotIn("plugins:main:swagger_ui", links)

    def test_gitlab_list_links_to_integration_detail(self):
        response = self.client.get(reverse("plugins:main:gitlabintegration_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.integration.get_absolute_url())

    def test_gitlab_detail_scopes_mappings_and_sync_logs_to_integration(self):
        other_integration = GitLabIntegration.objects.create(
            name="other",
            gitlab_url="https://gitlab.example.net",
            project_id="network/other",
            branch="main",
            access_token="token",
        )
        own_mapping = GitLabConfigMapping.objects.create(
            integration=self.integration,
            device=self.device,
            file_path="configs/own.yaml",
        )
        GitLabConfigMapping.objects.create(
            integration=other_integration,
            device=self.device,
            file_path="configs/other.yaml",
        )
        GitLabSyncLog.objects.create(
            integration=self.integration,
            mapping=own_mapping,
            device=self.device,
            direction=GitLabSyncLog.DIRECTION_PLUGIN_TO_GITLAB,
            file_path="configs/own.yaml",
            status=GitLabSyncLog.STATUS_SUCCESS,
            message="own log",
        )
        GitLabSyncLog.objects.create(
            integration=other_integration,
            device=self.device,
            direction=GitLabSyncLog.DIRECTION_PLUGIN_TO_GITLAB,
            file_path="configs/other.yaml",
            status=GitLabSyncLog.STATUS_SUCCESS,
            message="other log",
        )

        response = self.client.get(self.integration.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "configs/own.yaml")
        self.assertContains(response, "own log")
        self.assertNotContains(response, "configs/other.yaml")
        self.assertNotContains(response, "other log")

    def test_gitlab_form_rejects_page_url(self):
        form = forms.GitLabIntegrationForm(
            data={
                "name": "bad",
                "gitlab_url": "https://gitlab.com/users/sign_in",
                "project_id": "network/configs",
                "branch": "main",
                "root_path": "configs",
                "file_path_pattern": "{root_path}/{device_name}.yaml",
                "access_token": "token",
                "webhook_secret": "",
                "enabled": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("gitlab_url", form.errors)

    def test_cloudflare_html_error_is_summarized(self):
        html = """
        <!DOCTYPE html><html><head><title>Just a moment...</title></head>
        <body><script src="https://challenges.cloudflare.com/test"></script></body></html>
        """
        error = HTTPError("https://gitlab.com", 403, "Forbidden", {}, BytesIO(html.encode("utf-8")))

        message = GitLabClient._read_error(error)

        self.assertIn("Cloudflare challenge", message)
        self.assertNotIn("<html", message)

    def test_unexpected_html_response_is_summarized(self):
        message = GitLabClient._unexpected_response_message(
            "<html><body>/users/sign_in</body></html>",
            "text/html",
        )

        self.assertIn("HTML sign-in page", message)
        self.assertNotIn("<html", message)
