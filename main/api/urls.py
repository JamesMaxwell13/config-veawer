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
router.register("devices", DevicePlatformProfileViewSet, basename="device")
router.register("templates", CommandTemplateViewSet)
router.register("tasks", NetworkTaskViewSet)
router.register("configurations", ConfigurationBackupViewSet, basename="configuration")
router.register("scheduled-tasks", ScheduledTaskViewSet)
router.register("uml-configurations", UMLConfigurationViewSet)

urlpatterns = router.urls
