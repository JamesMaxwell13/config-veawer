from django import forms
import hashlib
import json
from urllib.parse import urlsplit
import yaml

from dcim.models import Device
from netbox.forms import NetBoxModelBulkEditForm, NetBoxModelForm
from utilities.forms import add_blank_choice
from utilities.forms.fields import DynamicModelChoiceField
from utilities.forms.rendering import FieldSet
from utilities.forms.widgets import BulkEditNullBooleanSelect, DateTimePicker

from ..domain.security import redact_secrets
from ..domain.configuration import ConfigValidationError
from ..application.config_validation import ConfigurationInputValidator
from ..application.configuration_yaml import ConfigurationYamlService
from ..models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    GitLabConfigMapping,
    GitLabIntegration,
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
        label="NetBox account username",
    )
    account_password = forms.CharField(
        label="NetBox account password",
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


class GitLabIntegrationForm(NetBoxModelForm):
    access_token = forms.CharField(widget=forms.PasswordInput(render_value=False))
    webhook_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["access_token"].required = False

    def clean(self):
        cleaned = super().clean() or self.cleaned_data
        if self.instance and self.instance.pk and not cleaned.get("access_token"):
            cleaned["access_token"] = self.instance.access_token
        if self.instance and self.instance.pk and not cleaned.get("webhook_secret"):
            cleaned["webhook_secret"] = self.instance.webhook_secret
        return cleaned

    def clean_gitlab_url(self):
        value = (self.cleaned_data.get("gitlab_url") or "").strip().rstrip("/")
        parsed = urlsplit(value)
        if parsed.query or parsed.fragment:
            raise forms.ValidationError("Provide the base GitLab URL without a query string or fragment.")
        if parsed.path and parsed.path != "/":
            raise forms.ValidationError("Provide a base GitLab URL like https://gitlab.com without a page path.")
        return value

    class Meta:
        model = GitLabIntegration
        fields = (
            "name",
            "gitlab_url",
            "project_id",
            "branch",
            "root_path",
            "file_path_pattern",
            "access_token",
            "webhook_secret",
            "enabled",
            "auto_apply",
            "tags",
        )


class GitLabConfigMappingForm(NetBoxModelForm):
    integration = DynamicModelChoiceField(queryset=GitLabIntegration.objects.all())
    device = DynamicModelChoiceField(queryset=Device.objects.all())
    configuration_backup = DynamicModelChoiceField(queryset=ConfigurationBackup.objects.all(), required=False)
    scheduled_task = DynamicModelChoiceField(queryset=ScheduledTask.objects.all(), required=False)

    class Meta:
        model = GitLabConfigMapping
        fields = (
            "integration",
            "device",
            "configuration_backup",
            "scheduled_task",
            "file_path",
            "last_gitlab_commit_sha",
            "sync_enabled",
            "tags",
        )


class DeviceCommandForm(forms.Form):
    commands = forms.CharField(
        label="CLI commands",
        help_text=(
            "One command per line. Commands will be sent to the device "
            "using the configured connection profile."
        ),
        widget=forms.Textarea(attrs={"rows": 10}),
    )


class CommandTemplateForm(NetBoxModelForm):
    BOUND_PARAMETER_CHOICES = (
        ("", "---------"),
        ("device.hostname", "device.hostname"),
        ("interface.enabled", "interface.enabled"),
        ("interface.description", "interface.description"),
        ("interface.mode", "interface.mode"),
        ("interface.access_vlan", "interface.access_vlan"),
        ("interface.native_vlan", "interface.native_vlan"),
        ("interface.tagged_vlans", "interface.tagged_vlans"),
        ("interface.mtu", "interface.mtu"),
        ("interface.speed", "interface.speed"),
        ("interface.duplex", "interface.duplex"),
        ("interface.poe_mode", "interface.poe_mode"),
        ("interface.poe_type", "interface.poe_type"),
        ("interface.ip_address", "interface.ip_address"),
    )

    bound_parameter = forms.ChoiceField(
        required=False,
        choices=BOUND_PARAMETER_CHOICES,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].help_text = (
            "Unique operation name, for example interface_l3 or access_vlan."
        )
        self.fields["command_body"].help_text = (
            "One CLI command per line. "
            "Use placeholders in braces: "
            "{interface}, {description}, {ip}, {mask}, {vlan_id}."
        )
        self.fields["bound_entity_type"].help_text = "Bound NetBox entity: device or interface."
        self.fields["bound_parameter"].help_text = "Specific bound entity parameter managed by this template."
        self.fields["bound_direction"].help_text = "Binding application direction."
        if self.instance and self.instance.pk and self.instance.bound_parameter and self.instance.bound_entity_type:
            current = f"{self.instance.bound_entity_type}.{self.instance.bound_parameter}"
            self.initial["bound_parameter"] = current
            known = {value for value, _label in self.fields["bound_parameter"].choices}
            if current not in known:
                self.fields["bound_parameter"].choices = (*self.fields["bound_parameter"].choices, (current, current))

    def clean(self):
        cleaned = super().clean() or self.cleaned_data
        bound_parameter = str(cleaned.get("bound_parameter") or "").strip()
        bound_entity_type = str(cleaned.get("bound_entity_type") or "").strip()
        if not bound_parameter:
            return cleaned
        if "." not in bound_parameter:
            if not bound_entity_type:
                raise forms.ValidationError("Set entity type for the selected bound parameter.")
            cleaned["bound_parameter"] = bound_parameter
            return cleaned

        entity, parameter = bound_parameter.split(".", 1)
        entity = entity.strip()
        parameter = parameter.strip()
        if bound_entity_type and bound_entity_type != entity:
            raise forms.ValidationError(
                "Bound entity type does not match the selected bound parameter."
            )
        cleaned["bound_entity_type"] = entity
        cleaned["bound_parameter"] = parameter
        return cleaned

    class Meta:
        model = CommandTemplate
        fields = (
            "name",
            "vendor",
            "platform",
            "operation_type",
            "bound_entity_type",
            "bound_parameter",
            "bound_direction",
            "binding_priority",
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
    bound_entity_type = forms.ChoiceField(
        choices=add_blank_choice(CommandTemplate.ENTITY_CHOICES),
        required=False,
    )
    bound_direction = forms.ChoiceField(
        choices=add_blank_choice(CommandTemplate.DIRECTION_CHOICES),
        required=False,
    )
    bound_parameter = forms.CharField(max_length=64, required=False)
    binding_priority = forms.IntegerField(min_value=1, required=False)
    is_active = forms.NullBooleanField(required=False, widget=BulkEditNullBooleanSelect())

    model = CommandTemplate
    fieldsets = (
        FieldSet(
            "vendor",
            "platform",
            "operation_type",
            "bound_entity_type",
            "bound_parameter",
            "bound_direction",
            "binding_priority",
            "is_active",
        ),
    )


class CommandTemplatePreviewForm(forms.Form):
    params = forms.CharField(
        label="Template parameters",
        required=False,
        help_text=(
            "YAML or JSON object with parameters, "
            "for example: interface: GigabitEthernet0/1"
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
                raise forms.ValidationError(f"Failed to parse YAML/JSON: {exc}") from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise forms.ValidationError("Parameters must be a mapping/object.")
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
        config_text = cleaned.get("config_text")
        if device and config_text:
            try:
                ConfigurationInputValidator.validate_backup_input_or_raise(
                    device=device,
                    config_text=config_text,
                )
            except ConfigValidationError as exc:
                raise forms.ValidationError(str(exc)) from exc
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
            from ..application.gitlab import GitLabIntegrationService

            GitLabIntegrationService.push_backup_to_gitlab(instance)
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
