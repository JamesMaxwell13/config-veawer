from django.urls import path
from netbox.views.generic import ObjectChangeLogView

from .models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)
from .presentation import views

urlpatterns = [
    path("credentials/", views.DeviceCredentialListView.as_view(), name="devicecredential_list"),
    path("credentials/add/", views.DeviceCredentialEditView.as_view(), name="devicecredential_add"),
    path("credentials/<int:pk>/", views.DeviceCredentialView.as_view(), name="devicecredential"),
    path("credentials/<int:pk>/reveal/", views.DeviceCredentialRevealView.as_view(), name="devicecredential_reveal"),
    path("credentials/<int:pk>/edit/", views.DeviceCredentialEditView.as_view(), name="devicecredential_edit"),
    path("credentials/<int:pk>/delete/", views.DeviceCredentialDeleteView.as_view(), name="devicecredential_delete"),
    path(
        "credentials/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="devicecredential_changelog",
        kwargs={"model": DeviceCredential},
    ),

    path("devices/", views.DevicePlatformProfileListView.as_view(), name="deviceplatformprofile_list"),
    path("devices/add/", views.DevicePlatformProfileEditView.as_view(), name="deviceplatformprofile_add"),
    path("devices/<int:pk>/", views.DevicePlatformProfileView.as_view(), name="deviceplatformprofile"),
    path("devices/<int:pk>/cli/", views.DevicePlatformProfileCLIView.as_view(), name="deviceplatformprofile_cli"),
    path("devices/<int:pk>/versions/", views.DevicePlatformProfileVersionsView.as_view(), name="deviceplatformprofile_versions"),
    path(
        "devices/<int:pk>/versions/diff/",
        views.DevicePlatformProfileVersionDiffView.as_view(),
        name="deviceplatformprofile_versions_diff",
    ),
    path(
        "devices/<int:pk>/refresh-config/",
        views.DevicePlatformProfileRefreshConfigView.as_view(),
        name="deviceplatformprofile_refresh_config",
    ),
    path(
        "devices/<int:pk>/terminal/",
        views.DevicePlatformProfileTerminalView.as_view(),
        name="deviceplatformprofile_terminal",
    ),
    path("devices/<int:pk>/edit/", views.DevicePlatformProfileEditView.as_view(), name="deviceplatformprofile_edit"),
    path("devices/<int:pk>/delete/", views.DevicePlatformProfileDeleteView.as_view(), name="deviceplatformprofile_delete"),
    path(
        "devices/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="deviceplatformprofile_changelog",
        kwargs={"model": DevicePlatformProfile},
    ),

    path("templates/", views.CommandTemplateListView.as_view(), name="commandtemplate_list"),
    path("templates/add/", views.CommandTemplateEditView.as_view(), name="commandtemplate_add"),
    path("templates/<int:pk>/", views.CommandTemplateView.as_view(), name="commandtemplate"),
    path("templates/<int:pk>/edit/", views.CommandTemplateEditView.as_view(), name="commandtemplate_edit"),
    path("templates/<int:pk>/preview/", views.CommandTemplatePreviewView.as_view(), name="commandtemplate_preview"),
    path("templates/<int:pk>/delete/", views.CommandTemplateDeleteView.as_view(), name="commandtemplate_delete"),
    path(
        "templates/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="commandtemplate_changelog",
        kwargs={"model": CommandTemplate},
    ),

    path("network-tasks/", views.NetworkTaskListView.as_view(), name="networktask_list"),
    path("network-tasks/add/", views.NetworkTaskEditView.as_view(), name="networktask_add"),
    path("network-tasks/<int:pk>/", views.NetworkTaskView.as_view(), name="networktask"),
    path("network-tasks/<int:pk>/edit/", views.NetworkTaskEditView.as_view(), name="networktask_edit"),
    path("network-tasks/<int:pk>/delete/", views.NetworkTaskDeleteView.as_view(), name="networktask_delete"),
    path(
        "network-tasks/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="networktask_changelog",
        kwargs={"model": NetworkTask},
    ),

    path("configurations/", views.ConfigurationBackupListView.as_view(), name="configurationbackup_list"),
    path("configurations/add/", views.ConfigurationBackupEditView.as_view(), name="configurationbackup_add"),
    path("configurations/<int:pk>/", views.ConfigurationBackupView.as_view(), name="configurationbackup"),
    path("configurations/<int:pk>/yaml/", views.ConfigurationBackupYAMLView.as_view(), name="configurationbackup_yaml"),
    path("configurations/<int:pk>/edit/", views.ConfigurationBackupEditView.as_view(), name="configurationbackup_edit"),
    path("configurations/<int:pk>/delete/", views.ConfigurationBackupDeleteView.as_view(), name="configurationbackup_delete"),
    path(
        "configurations/<int:pk>/refresh/",
        views.ConfigurationBackupRefreshView.as_view(),
        name="configurationbackup_refresh",
    ),
    path(
        "configurations/<int:pk>/activate/",
        views.ConfigurationBackupRestoreView.as_view(),
        name="configurationbackup_restore",
    ),
    path(
        "configurations/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="configurationbackup_changelog",
        kwargs={"model": ConfigurationBackup},
    ),

    path("tasks/", views.ScheduledTaskListView.as_view(), name="scheduledtask_list"),
    path("tasks/add/", views.ScheduledTaskEditView.as_view(), name="scheduledtask_add"),
    path("tasks/<int:pk>/", views.ScheduledTaskView.as_view(), name="scheduledtask"),
    path("tasks/<int:pk>/edit/", views.ScheduledTaskEditView.as_view(), name="scheduledtask_edit"),
    path("tasks/<int:pk>/delete/", views.ScheduledTaskDeleteView.as_view(), name="scheduledtask_delete"),
    path("tasks/<int:pk>/run/", views.ScheduledTaskRunNowView.as_view(), name="scheduledtask_run"),
    path("tasks/<int:pk>/preview/", views.ScheduledTaskPreviewView.as_view(), name="scheduledtask_preview"),
    path(
        "tasks/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="scheduledtask_changelog",
        kwargs={"model": ScheduledTask},
    ),

    path("uml/", views.UMLConfigurationListView.as_view(), name="umlconfiguration_list"),
    path("uml/add/", views.UMLConfigurationEditView.as_view(), name="umlconfiguration_add"),
    path("uml/<int:pk>/", views.UMLConfigurationView.as_view(), name="umlconfiguration"),
    path("uml/<int:pk>/edit/", views.UMLConfigurationEditView.as_view(), name="umlconfiguration_edit"),
    path("uml/<int:pk>/delete/", views.UMLConfigurationDeleteView.as_view(), name="umlconfiguration_delete"),
    path("uml/<int:pk>/render/", views.UMLConfigurationRenderView.as_view(), name="umlconfiguration_render"),
    path("uml/<int:pk>/preview/", views.UMLConfigurationPreviewView.as_view(), name="umlconfiguration_preview"),
    path(
        "uml/<int:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="umlconfiguration_changelog",
        kwargs={"model": UMLConfiguration},
    ),

    # Backward-compatible aliases for older internal links.
    path("devices/", views.DevicePlatformProfileListView.as_view(), name="device_list"),
    path("devices/add/", views.DevicePlatformProfileEditView.as_view(), name="device_add"),
    path("devices/<int:pk>/", views.DevicePlatformProfileView.as_view(), name="device"),
    path("devices/<int:pk>/cli/", views.DevicePlatformProfileCLIView.as_view(), name="device_cli"),
    path("devices/<int:pk>/versions/", views.DevicePlatformProfileVersionsView.as_view(), name="device_versions"),
    path("devices/<int:pk>/refresh-config/", views.DevicePlatformProfileRefreshConfigView.as_view(), name="device_refresh_config"),
    path("devices/<int:pk>/terminal/", views.DevicePlatformProfileTerminalView.as_view(), name="device_terminal"),
    path("devices/<int:pk>/edit/", views.DevicePlatformProfileEditView.as_view(), name="device_edit"),
    path("devices/<int:pk>/delete/", views.DevicePlatformProfileDeleteView.as_view(), name="device_delete"),

    path("configurations/", views.ConfigurationBackupListView.as_view(), name="configuration_list"),
    path("configurations/add/", views.ConfigurationBackupEditView.as_view(), name="configuration_add"),
    path("configurations/<int:pk>/", views.ConfigurationBackupView.as_view(), name="configuration"),
    path("configurations/<int:pk>/yaml/", views.ConfigurationBackupYAMLView.as_view(), name="configuration_yaml"),
    path("configurations/<int:pk>/edit/", views.ConfigurationBackupEditView.as_view(), name="configuration_edit"),
    path("configurations/<int:pk>/delete/", views.ConfigurationBackupDeleteView.as_view(), name="configuration_delete"),
    path("configurations/<int:pk>/refresh/", views.ConfigurationBackupRefreshView.as_view(), name="configuration_refresh"),
    path("configurations/<int:pk>/activate/", views.ConfigurationBackupRestoreView.as_view(), name="configuration_activate"),
]
