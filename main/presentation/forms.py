from django import forms
import hashlib
import json
import yaml

from dcim.models import Device
from netbox.forms import NetBoxModelBulkEditForm, NetBoxModelForm
from utilities.forms import add_blank_choice
from utilities.forms.fields import DynamicModelChoiceField
from utilities.forms.rendering import FieldSet
from utilities.forms.widgets import BulkEditNullBooleanSelect, DateTimePicker

from ..domain.security import redact_secrets
from ..application.configuration_yaml import ConfigurationYamlService
from ..models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)


YAML_EDITOR_ATTRS = {
    "class": "font-monospace yaml-editor",
    "data-yaml-editor": "true",
    "spellcheck": "false",
    "wrap": "off",
}


class DeviceCredentialForm(NetBoxModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=False))
    enable_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["password"].required = False

    def clean(self):
        cleaned = super().clean() or self.cleaned_data
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
    account_username = forms.CharField(
        label="Логин учетной записи NetBox",
    )
    account_password = forms.CharField(
        label="Пароль учетной записи NetBox",
        widget=forms.PasswordInput(render_value=False),
    )


class DeviceCredentialBulkEditForm(NetBoxModelBulkEditForm):
    auth_method = forms.ChoiceField(
        choices=add_blank_choice(DeviceCredential.AUTH_CHOICES),
        required=False,
    )
    username = forms.CharField(max_length=128, required=False)
    ssh_port = forms.IntegerField(min_value=1, required=False)
    timeout = forms.IntegerField(min_value=1, required=False)
    use_enable = forms.NullBooleanField(required=False, widget=BulkEditNullBooleanSelect())
    is_active = forms.NullBooleanField(required=False, widget=BulkEditNullBooleanSelect())

    model = DeviceCredential
    fieldsets = (
        FieldSet("auth_method", "username", "ssh_port", "timeout", "use_enable", "is_active"),
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


class DevicePlatformProfileBulkEditForm(NetBoxModelBulkEditForm):
    credential = DynamicModelChoiceField(queryset=DeviceCredential.objects.all(), required=False)
    vendor = forms.ChoiceField(
        choices=add_blank_choice(DevicePlatformProfile.VENDOR_CHOICES),
        required=False,
    )
    platform = forms.ChoiceField(
        choices=add_blank_choice(DevicePlatformProfile.PLATFORM_CHOICES),
        required=False,
    )
    management_ip = forms.GenericIPAddressField(protocol="IPv4", required=False)
    command_timeout = forms.IntegerField(min_value=1, required=False)
    enabled = forms.NullBooleanField(required=False, widget=BulkEditNullBooleanSelect())

    model = DevicePlatformProfile
    fieldsets = (
        FieldSet("credential", "vendor", "platform", "management_ip", "command_timeout", "enabled"),
    )
    nullable_fields = ("management_ip",)


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


class CommandTemplateBulkEditForm(NetBoxModelBulkEditForm):
    vendor = forms.CharField(max_length=100, required=False)
    platform = forms.CharField(max_length=100, required=False)
    operation_type = forms.ChoiceField(
        choices=add_blank_choice(CommandTemplate.OP_CHOICES),
        required=False,
    )
    is_active = forms.NullBooleanField(required=False, widget=BulkEditNullBooleanSelect())

    model = CommandTemplate
    fieldsets = (
        FieldSet("vendor", "platform", "operation_type", "is_active"),
    )


class CommandTemplatePreviewForm(forms.Form):
    params = forms.CharField(
        label="Параметры шаблона",
        required=False,
        help_text=(
            "YAML или JSON mapping с параметрами, "
            "например: interface: GigabitEthernet0/1"
        ),
        widget=forms.Textarea(attrs={**YAML_EDITOR_ATTRS, "rows": 8}),
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
        widgets = {
            "plan_yaml": forms.Textarea(attrs={**YAML_EDITOR_ATTRS, "rows": 18}),
        }


class ConfigurationBackupBulkEditForm(NetBoxModelBulkEditForm):
    task = DynamicModelChoiceField(queryset=NetworkTask.objects.all(), required=False)
    source = forms.CharField(max_length=64, required=False)
    redacted = forms.NullBooleanField(required=False, widget=BulkEditNullBooleanSelect())

    model = ConfigurationBackup
    fieldsets = (
        FieldSet("task", "source", "redacted"),
    )
    nullable_fields = ("task",)


class ConfigurationBackupForm(NetBoxModelForm):
    device = DynamicModelChoiceField(queryset=Device.objects.all())
    task = DynamicModelChoiceField(queryset=NetworkTask.objects.all(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["version"].required = False
        self.fields["source"].initial = self.fields["source"].initial or "manual"

    def clean(self):
        cleaned = super().clean() or self.cleaned_data
        device = cleaned.get("device")
        if device and not cleaned.get("version"):
            latest = ConfigurationBackup.objects.filter(device=device).order_by("-version").first()
            cleaned["version"] = 1 if latest is None else latest.version + 1
        return cleaned

    def save(self, *args, **kwargs):
        instance = super().save(commit=False)
        raw_config = redact_secrets(instance.config_text)
        instance.config_text = (
            raw_config
            if ConfigurationYamlService.is_yaml_config(raw_config)
            else ConfigurationYamlService.running_config_to_yaml(instance.device, raw_config, source=instance.source or "manual")
        )
        instance.config_checksum = hashlib.sha256(instance.config_text.encode("utf-8")).hexdigest()
        instance.redacted = True
        if not instance.source:
            instance.source = "manual"
        if not instance.version_name:
            from ..infrastructure.vcs import ConfigurationVCS

            instance.version_name = ConfigurationVCS.build_unique_version_name(
                instance.device,
                exclude_pk=instance.pk,
            )
        if kwargs.get("commit", True):
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = ConfigurationBackup
        fields = ("device", "task", "version", "version_name", "config_text", "source", "tags")
        widgets = {
            "config_text": forms.Textarea(attrs={**YAML_EDITOR_ATTRS, "rows": 24}),
        }


class ScheduledTaskForm(NetBoxModelForm):
    target_device = DynamicModelChoiceField(queryset=Device.objects.all())

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
        widgets = {
            "task": forms.Textarea(attrs={**YAML_EDITOR_ATTRS, "rows": 14}),
        }


class ScheduledTaskBulkEditForm(NetBoxModelBulkEditForm):
    task_type = forms.ChoiceField(
        choices=add_blank_choice(ScheduledTask.TYPE_CHOICES),
        required=False,
    )
    target_device = DynamicModelChoiceField(queryset=Device.objects.all(), required=False)
    schedule_time = forms.DateTimeField(required=False, widget=DateTimePicker())
    run_every_seconds = forms.IntegerField(min_value=1, required=False)
    max_retries = forms.IntegerField(min_value=0, required=False)
    status = forms.ChoiceField(
        choices=add_blank_choice(ScheduledTask.STATUS_CHOICES),
        required=False,
    )

    model = ScheduledTask
    fieldsets = (
        FieldSet("task_type", "target_device", "schedule_time", "run_every_seconds", "max_retries", "status"),
    )
    nullable_fields = ("run_every_seconds",)


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
