from django.utils.html import format_html
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
    actions = ActionsColumn(
        extra_buttons="""
            <a class="btn btn-sm btn-danger"
               href="{% url 'plugins:main:devicecredential_reveal' pk=record.pk %}"
               title="Показать пароль"
               aria-label="Показать пароль">
              <i class="mdi mdi-lock-open-variant"></i>
            </a>
        """
    )

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
    version_name = tables.Column(verbose_name="Название")

    def render_task(self, value, record):
        return value or "-"

    def render_version_name(self, value, record):
        if not value:
            return "-"
        return format_html('<a href="{}">{}</a>', record.get_absolute_url(), value)

    def render_commit_hash(self, value):
        return self._render_short_hash(value)

    def render_config_checksum(self, value):
        return self._render_short_hash(value)

    @staticmethod
    def _render_short_hash(value):
        if not value:
            return "-"
        return format_html("<code title=\"{}\">{}</code>", value, value[:12])

    class Meta(NetBoxTable.Meta):
        model = ConfigurationBackup
        fields = ("device", "version", "version_name", "source", "commit_hash", "config_checksum", "created")


class DevicePlatformProfileTable(NetBoxTable):
    device = TemplateColumn(
        template_code='<a href="{{ record.get_absolute_url }}">{{ record.device }}</a>',
        verbose_name="Профиль Config Weaver",
    )
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
    task_name = tables.Column(verbose_name="Название")
    task = tables.Column(verbose_name="Таск (YAML)")

    def render_task_name(self, value, record):
        return format_html('<a href="{}">{}</a>', record.get_absolute_url(), value)

    def render_task(self, value):
        if not value:
            return "-"
        compact = " ".join(value.split())
        if len(compact) > 100:
            compact = compact[:100] + "..."
        return format_html("<code title=\"{}\">{}</code>", value, compact)

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
