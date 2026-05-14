import json

from django.test import TestCase, override_settings
from django.urls import reverse
from users.models import User


@override_settings(PLUGINS_CONFIG={"main": {"secret_key": "test-secret-key"}})
class ConfigWeaverSwaggerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password")
        self.client.force_login(self.user)

    def test_swagger_ui_page_loads(self):
        response = self.client.get(reverse("plugins:main:swagger_ui"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "config-weaver API")
        self.assertContains(response, "SwaggerUIBundle")
        self.assertContains(response, "api/schema/")

    def test_swagger_schema_contains_plugin_api_paths(self):
        response = self.client.get(reverse("plugins:main:swagger_schema"), {"format": "json"})

        self.assertEqual(response.status_code, 200)
        schema = json.loads(response.content)
        paths = schema["paths"]

        self.assertIn("openapi", schema)
        self.assertIn("/api/plugins/config-weaver/configurations/", paths)
        self.assertIn("/api/plugins/config-weaver/configurations/by_device/", paths)
        self.assertIn("/api/plugins/config-weaver/configurations/compare/", paths)

    def test_swagger_schema_documents_configuration_action_parameters(self):
        response = self.client.get(reverse("plugins:main:swagger_schema"), {"format": "json"})

        self.assertEqual(response.status_code, 200)
        schema = json.loads(response.content)

        by_device_parameters = {
            parameter["name"]
            for parameter in schema["paths"]["/api/plugins/config-weaver/configurations/by_device/"]["get"]["parameters"]
        }
        compare_parameters = {
            parameter["name"]
            for parameter in schema["paths"]["/api/plugins/config-weaver/configurations/compare/"]["get"]["parameters"]
        }

        self.assertIn("device_id", by_device_parameters)
        self.assertIn("from", compare_parameters)
        self.assertIn("to", compare_parameters)
