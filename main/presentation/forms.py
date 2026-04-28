from django import forms

from dcim.models import Device
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from ..models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)


class DeviceCredentialForm(NetBoxModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=False))
    enable_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["password"].required = False

    def clean(self):
        cleaned = super().clean()
        if self.instance and self.instance.pk and not cleaned.get("password"):
            cleaned["password"] = self.instance.password
        if self.instance and self.instance.pk and not cleaned.get("enable_secret"):
            cleaned["enable_secret"] = self.instance.enable_secret
        return cleaned

    class Meta:
        model = DeviceCredential
        fields = (
            "name",
            "auth_method",
            "username",
            "password",
            "enable_secret",
            "ssh_port",
            "timeout",
            "use_enable",
            "is_active",
            "tags",
        )


class DevicePlatformProfileForm(NetBoxModelForm):
    device = DynamicModelChoiceField(queryset=Device.objects.all())
    credential = DynamicModelChoiceField(queryset=DeviceCredential.objects.all())

    class Meta:
        model = DevicePlatformProfile
        fields = (
            "device",
            "credential",
            "vendor",
            "platform",
            "management_ip",
            "command_timeout",
            "enabled",
            "tags",
        )


class CommandTemplateForm(NetBoxModelForm):
    class Meta:
        model = CommandTemplate
        fields = (
            "name",
            "vendor",
            "platform",
            "operation_type",
            "command_body",
            "is_active",
            "revision",
            "tags",
        )


class NetworkTaskForm(NetBoxModelForm):
    class Meta:
        model = NetworkTask
        fields = ("name", "description", "device_task", "plan_yaml", "enabled", "tags")


class ConfigurationBackupForm(NetBoxModelForm):
    class Meta:
        model = ConfigurationBackup
        fields = ("device", "task", "version", "config_text", "source", "commit_hash", "tags")


class ScheduledTaskForm(NetBoxModelForm):
    target_device = DynamicModelChoiceField(queryset=Device.objects.all())
    task = DynamicModelChoiceField(queryset=NetworkTask.objects.all(), required=False)

    class Meta:
        model = ScheduledTask
        fields = (
            "task_name",
            "task_type",
            "target_device",
            "task",
            "schedule_time",
            "run_every_seconds",
            "max_retries",
            "status",
            "result_message",
            "tags",
        )


class UMLConfigurationForm(NetBoxModelForm):
    class Meta:
        model = UMLConfiguration
        fields = (
            "name",
            "diagram_type",
            "task",
            "device",
            "source_text",
            "rendered_svg",
            "revision",
            "is_active",
            "tags",
        )
