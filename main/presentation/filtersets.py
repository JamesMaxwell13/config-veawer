from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet
from utilities.filtersets import register_filterset

from ..models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    GitLabConfigMapping,
    GitLabIntegration,
    GitLabSyncLog,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)


@register_filterset
class DeviceCredentialFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = DeviceCredential
        fields = ("id", "name", "username", "auth_method", "ssh_port", "use_enable", "is_active")


@register_filterset
class DevicePlatformProfileFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = DevicePlatformProfile
        fields = ("id", "device", "credential", "vendor", "platform", "enabled")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device__name__icontains=value)
            | Q(device__serial__icontains=value)
            | Q(management_ip__icontains=value)
        )


@register_filterset
class CommandTemplateFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = CommandTemplate
        fields = (
            "id",
            "name",
            "vendor",
            "platform",
            "operation_type",
            "bound_entity_type",
            "bound_parameter",
            "bound_direction",
        )


@register_filterset
class GitLabIntegrationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = GitLabIntegration
        fields = ("id", "name", "gitlab_url", "project_id", "branch", "enabled", "auto_apply")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(project_id__icontains=value) | Q(gitlab_url__icontains=value))


@register_filterset
class GitLabConfigMappingFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = GitLabConfigMapping
        fields = ("id", "integration", "device", "configuration_backup", "file_path", "sync_enabled")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(file_path__icontains=value) | Q(device__name__icontains=value))


@register_filterset
class GitLabSyncLogFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = GitLabSyncLog
        fields = ("id", "integration", "mapping", "device", "direction", "status", "file_path", "commit_sha", "created")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(file_path__icontains=value) | Q(message__icontains=value) | Q(device__name__icontains=value))


@register_filterset
class NetworkTaskFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NetworkTask
        fields = ("id", "name", "device_task", "enabled")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value) | Q(device_task__icontains=value))


@register_filterset
class ConfigurationBackupFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = ConfigurationBackup
        fields = ("id", "device", "task", "version", "source", "commit_hash", "config_checksum", "redacted", "created")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device__name__icontains=value)
            | Q(version_name__icontains=value)
            | Q(source__icontains=value)
            | Q(config_checksum__icontains=value)
        )


@register_filterset
class ScheduledTaskFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = ScheduledTask
        fields = ("id", "task_name", "task_type", "target_device", "status")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(task_name__icontains=value) | Q(result_message__icontains=value))


@register_filterset
class UMLConfigurationFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = UMLConfiguration
        fields = ("id", "name", "diagram_type", "task", "device", "revision", "is_active", "checksum")
