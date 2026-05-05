from netbox.tables import NetBoxTable
from netbox.tables.columns import ActionsColumn, TemplateColumn
import django_tables2 as tables

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
        fields = ("name", "vendor", "platform", "operation_type", "revision", "is_active", "created", "last_updated")


class NetworkTaskTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = NetworkTask
        fields = ("name", "device_task", "enabled", "created", "last_updated")


class ConfigurationBackupTable(NetBoxTable):
    task = tables.Column(empty_values=(), verbose_name="Сценарий")

    def render_task(self, value, record):
        return value or "-"

    class Meta(NetBoxTable.Meta):
        model = ConfigurationBackup
        fields = ("device", "version", "version_name", "source", "commit_hash", "config_checksum", "created")


class DevicePlatformProfileTable(NetBoxTable):
    device = tables.Column(linkify=True, verbose_name="Профиль Config Weaver")
    netbox_device = TemplateColumn(
        template_code='<a href="{{ record.device.get_absolute_url }}">{{ record.device }}</a>',
        verbose_name="Устройство NetBox",
        orderable=False,
    )
    actions = ActionsColumn(
        extra_buttons="""
            <a class="btn btn-sm btn-primary"
               href="{% url 'plugins:main:deviceplatformprofile_terminal' pk=record.pk %}"
               title="Терминал"
               aria-label="Терминал">
              <i class="mdi mdi-console"></i>
            </a>
        """
    )

    class Meta(NetBoxTable.Meta):
        model = DevicePlatformProfile
        fields = ("device", "netbox_device", "credential", "platform", "management_ip", "enabled", "last_updated")


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
