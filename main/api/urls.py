from netbox.api.routers import NetBoxRouter

from .views import (
    CommandTemplateViewSet,
    ConfigurationBackupViewSet,
    DeviceCredentialViewSet,
    DevicePlatformProfileViewSet,
    NetworkTaskViewSet,
    ScheduledTaskViewSet,
    UMLConfigurationViewSet,
)

app_name = "main"

router = NetBoxRouter()
router.register("credentials", DeviceCredentialViewSet)
router.register("profiles", DevicePlatformProfileViewSet)
router.register("templates", CommandTemplateViewSet)
router.register("tasks", NetworkTaskViewSet)
router.register("backups", ConfigurationBackupViewSet)
router.register("scheduled-tasks", ScheduledTaskViewSet)
router.register("uml-configurations", UMLConfigurationViewSet)

urlpatterns = router.urls
