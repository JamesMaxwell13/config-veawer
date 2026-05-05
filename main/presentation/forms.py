from django import forms
import hashlib
import json
import yaml

from dcim.models import Device
from netbox.forms import NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from ..domain.security import redact_secrets
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


class CredentialRevealForm(forms.Form):
    account_password = forms.CharField(
        label="Пароль учетной записи NetBox",
        widget=forms.PasswordInput(render_value=False),
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


class DeviceCommandForm(forms.Form):
    commands = forms.CharField(
        label="Команды CLI",
        help_text=(
            "Одна команда на строку. Команды будут отправлены на устройство "
            "через настроенный профиль подключения."
        ),
        widget=forms.Textarea(attrs={"rows": 10}),
    )


class CommandTemplateForm(NetBoxModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].help_text = (
            "Уникальное имя операции, например interface_l3 или access_vlan."
        )
        self.fields["command_body"].help_text = (
            "Одна CLI-команда на строку. "
            "Параметры указываются в фигурных скобках: "
            "{interface}, {description}, {ip}, {mask}, {vlan_id}."
        )

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


class CommandTemplatePreviewForm(forms.Form):
    params = forms.CharField(
        label="Параметры шаблона",
        required=False,
        help_text=(
            "YAML или JSON mapping с параметрами, "
            "например: interface: GigabitEthernet0/1"
        ),
        widget=forms.Textarea(attrs={"rows": 8}),
    )

    def clean_params(self):
        raw = self.cleaned_data["params"]
        if not raw.strip():
            return {}
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError(f"Не удалось разобрать YAML/JSON: {exc}") from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise forms.ValidationError("Параметры должны быть mapping/object.")
        return data


class NetworkTaskForm(NetBoxModelForm):
    class Meta:
        model = NetworkTask
        fields = ("name", "description", "device_task", "plan_yaml", "enabled", "tags")


class ConfigurationBackupForm(NetBoxModelForm):
    device = DynamicModelChoiceField(queryset=Device.objects.all())
    task = DynamicModelChoiceField(queryset=NetworkTask.objects.all(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["version"].required = False
        self.fields["source"].initial = self.fields["source"].initial or "manual"

    def clean(self):
        cleaned = super().clean()
        device = cleaned.get("device")
        if device and not cleaned.get("version"):
            latest = ConfigurationBackup.objects.filter(device=device).order_by("-version").first()
            cleaned["version"] = 1 if latest is None else latest.version + 1
        return cleaned

    def save(self, *args, **kwargs):
        instance = super().save(commit=False)
        instance.config_text = redact_secrets(instance.config_text)
        instance.config_checksum = hashlib.sha256(instance.config_text.encode("utf-8")).hexdigest()
        instance.redacted = True
        if not instance.source:
            instance.source = "manual"
        if not instance.version_name:
            from ..infrastructure.vcs import ConfigurationVCS

            instance.version_name = ConfigurationVCS.build_version_name(instance.device)
        if kwargs.get("commit", True):
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = ConfigurationBackup
        fields = ("device", "task", "version", "version_name", "config_text", "source", "tags")


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
