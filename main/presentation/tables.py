from netbox.tables import NetBoxTable

from ..models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)


class DeviceCredentialTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = DeviceCredential
        fields = ("name", "username", "ssh_port", "timeout", "use_enable", "created", "last_updated")


class CommandTemplateTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = CommandTemplate
        fields = ("name", "vendor", "platform", "operation_type", "created", "last_updated")


class NetworkTaskTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = NetworkTask
        fields = ("name", "device_task", "enabled", "created", "last_updated")


class ConfigurationBackupTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = ConfigurationBackup
        fields = ("device", "task", "version", "version_name", "source", "commit_hash", "config_checksum", "created")


class DevicePlatformProfileTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = DevicePlatformProfile
        fields = ("device", "credential", "vendor", "platform", "management_ip", "enabled", "last_updated")


class ScheduledTaskTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = ScheduledTask
        fields = (
            "task_name",
            "task_type",
            "target_device",
            "task",
            "schedule_time",
            "status",
            "run_every_seconds",
            "max_retries",
            "retry_count",
            "last_run_at",
        )


class UMLConfigurationTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = UMLConfiguration
        fields = ("name", "diagram_type", "task", "device", "revision", "is_active", "checksum", "last_updated")
