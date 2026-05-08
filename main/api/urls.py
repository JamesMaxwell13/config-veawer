from netbox.api.routers import NetBoxRouter
from django.urls import path

from .views import (
    CommandTemplateViewSet,
    ConfigurationBackupViewSet,
    DeviceCredentialViewSet,
    DevicePlatformProfileViewSet,
    GitLabConfigMappingViewSet,
    GitLabIntegrationViewSet,
    GitLabSyncLogViewSet,
    GitLabWebhookView,
    NetworkTaskViewSet,
    ScheduledTaskViewSet,
    UMLConfigurationViewSet,
)

app_name = "main"

router = NetBoxRouter()
router.register("credentials", DeviceCredentialViewSet)
router.register("devices", DevicePlatformProfileViewSet, basename="device")
router.register("gitlab-integrations", GitLabIntegrationViewSet, basename="gitlabintegration")
router.register("gitlab-mappings", GitLabConfigMappingViewSet, basename="gitlabconfigmapping")
router.register("gitlab-sync-logs", GitLabSyncLogViewSet, basename="gitlabsynclog")
router.register("templates", CommandTemplateViewSet)
router.register("tasks", NetworkTaskViewSet)
router.register("configurations", ConfigurationBackupViewSet, basename="configuration")
router.register("scheduled-tasks", ScheduledTaskViewSet)
router.register("uml-configurations", UMLConfigurationViewSet)

urlpatterns = [
    *router.urls,
    path("gitlab/webhook/", GitLabWebhookView.as_view(), name="gitlab_webhook"),
]
