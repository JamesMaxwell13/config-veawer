from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import models
from django.urls import reverse
from django.utils import timezone
from netbox.models import NetBoxModel

from .infrastructure.crypto import decrypt_value, encrypt_value, is_encrypted


class DeviceCredential(NetBoxModel):
    class AuthMethod(models.TextChoices):
        PASSWORD = "password", "Username/Password"

    AUTH_PASSWORD = AuthMethod.PASSWORD.value
    AUTH_CHOICES = AuthMethod.choices

    name = models.CharField(max_length=100, unique=True)
    auth_method = models.CharField(max_length=32, choices=AuthMethod.choices, default=AuthMethod.PASSWORD.value)
    username = models.CharField(max_length=128)
    password = models.CharField(max_length=255)
    enable_secret = models.CharField(max_length=255, blank=True)
    ssh_port = models.PositiveIntegerField(default=22)
    timeout = models.PositiveIntegerField(default=30)
    use_enable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Device credential"
        verbose_name_plural = "Device credentials"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:main:devicecredential", kwargs={"pk": self.pk})

    @property
    def password_plain(self) -> str:
        return decrypt_value(self.password)

    @property
    def enable_secret_plain(self) -> str:
        return decrypt_value(self.enable_secret)

    def save(self, *args, **kwargs):
        if self.password and not is_encrypted(self.password):
            self.password = encrypt_value(self.password)
        if self.enable_secret and not is_encrypted(self.enable_secret):
            self.enable_secret = encrypt_value(self.enable_secret)
        super().save(*args, **kwargs)


class GitLabIntegration(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    gitlab_url = models.URLField()
    project_id = models.CharField(max_length=255)
    branch = models.CharField(max_length=255, default="main")
    root_path = models.CharField(max_length=255, default="configs")
    file_path_pattern = models.CharField(
        max_length=512,
        default="{root_path}/{site_slug}/{location_slug}/{rack_slug}/{device_name}.yaml",
    )
    access_token = models.CharField(max_length=512)
    webhook_secret = models.CharField(max_length=512, blank=True)
    enabled = models.BooleanField(default=True)
    auto_apply = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "GitLab integration"
        verbose_name_plural = "GitLab integrations"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:main:gitlabintegration", kwargs={"pk": self.pk})

    @property
    def access_token_plain(self) -> str:
        return decrypt_value(self.access_token)

    @property
    def webhook_secret_plain(self) -> str:
        return decrypt_value(self.webhook_secret)

    def save(self, *args, **kwargs):
        if self.access_token and not is_encrypted(self.access_token):
            self.access_token = encrypt_value(self.access_token)
        if self.webhook_secret and not is_encrypted(self.webhook_secret):
            self.webhook_secret = encrypt_value(self.webhook_secret)
        super().save(*args, **kwargs)


class CommandTemplate(NetBoxModel):
    class OperationType(models.TextChoices):
        INTERFACE = "interface", "Interface config"
        VLAN = "vlan", "VLAN config"
        IP = "ip", "IP config"
        CUSTOM = "custom", "Custom"

    class EntityType(models.TextChoices):
        DEVICE = "device", "Device"
        INTERFACE = "interface", "Interface"

    class BindingDirection(models.TextChoices):
        BOTH = "both", "Both"
        NB_TO_CFG = "nb_to_cfg", "NetBox -> Config"
        CFG_TO_NB = "cfg_to_nb", "Config -> NetBox"

    OP_INTERFACE = OperationType.INTERFACE.value
    OP_VLAN = OperationType.VLAN.value
    OP_IP = OperationType.IP.value
    OP_CUSTOM = OperationType.CUSTOM.value
    OP_CHOICES = OperationType.choices
    ENTITY_DEVICE = EntityType.DEVICE.value
    ENTITY_INTERFACE = EntityType.INTERFACE.value
    ENTITY_CHOICES = EntityType.choices
    DIRECTION_BOTH = BindingDirection.BOTH.value
    DIRECTION_NB_TO_CFG = BindingDirection.NB_TO_CFG.value
    DIRECTION_CFG_TO_NB = BindingDirection.CFG_TO_NB.value
    DIRECTION_CHOICES = BindingDirection.choices

    name = models.CharField(max_length=100)
    vendor = models.CharField(max_length=100)
    platform = models.CharField(max_length=100)
    operation_type = models.CharField(max_length=32, choices=OperationType.choices, default=OperationType.CUSTOM.value)
    bound_entity_type = models.CharField(max_length=16, choices=EntityType.choices, blank=True)
    bound_parameter = models.CharField(max_length=64, blank=True)
    bound_direction = models.CharField(max_length=16, choices=BindingDirection.choices, default=BindingDirection.BOTH.value)
    binding_priority = models.PositiveIntegerField(default=100)
    command_body = models.TextField()
    is_active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("vendor", "platform", "operation_type", "name")
        unique_together = ("name", "vendor", "platform", "operation_type")
        verbose_name = "Command template"
        verbose_name_plural = "Command templates"

    def __str__(self) -> str:
        return f"{self.name} ({self.vendor}/{self.platform})"

    def get_absolute_url(self):
        return reverse("plugins:main:commandtemplate", kwargs={"pk": self.pk})

    def render(self, params: dict) -> str:
        return self.command_body.format(**params)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete("cw:templates:active")

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        cache.delete("cw:templates:active")
        return result


class NetworkTask(NetBoxModel):
    class PlanFormat(models.TextChoices):
        YAML = "yaml", "YAML"

    PLAN_YAML = PlanFormat.YAML.value
    PLAN_CHOICES = PlanFormat.choices

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    device_task = models.CharField(max_length=255)
    plan_format = models.CharField(max_length=16, choices=PlanFormat.choices, default=PlanFormat.YAML.value)
    plan_yaml = models.TextField()
    plan_checksum = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField(default=True)
    last_validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Network task"
        verbose_name_plural = "Network tasks"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:main:networktask", kwargs={"pk": self.pk})

    @property
    def short_description(self) -> str:
        if not self.description:
            return ""
        return self.description[:100]


class ConfigurationBackup(NetBoxModel):
    device = models.ForeignKey("dcim.Device", on_delete=models.CASCADE, related_name="config_backups")
    task = models.ForeignKey(
        NetworkTask, on_delete=models.SET_NULL, null=True, blank=True, related_name="backups"
    )
    version = models.PositiveIntegerField(default=1)
    version_name = models.CharField(max_length=128, blank=True)
    config_text = models.TextField()
    source = models.CharField(max_length=64, default="runtime")
    commit_hash = models.CharField(max_length=64, blank=True)
    config_checksum = models.CharField(max_length=64, blank=True)
    redacted = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created",)
        unique_together = ("device", "version")
        verbose_name = "Configuration backup"
        verbose_name_plural = "Configuration backups"

    def __str__(self) -> str:
        return f"{self.device} v{self.version}"

    def get_absolute_url(self):
        return reverse("plugins:main:configurationbackup", kwargs={"pk": self.pk})


class GitLabConfigMapping(NetBoxModel):
    integration = models.ForeignKey(
        GitLabIntegration,
        on_delete=models.CASCADE,
        related_name="config_mappings",
    )
    device = models.ForeignKey("dcim.Device", on_delete=models.CASCADE, related_name="gitlab_config_mappings")
    configuration_backup = models.ForeignKey(
        ConfigurationBackup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gitlab_mappings",
    )
    scheduled_task = models.ForeignKey(
        "ScheduledTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gitlab_mappings",
    )
    file_path = models.CharField(max_length=1024)
    last_gitlab_commit_sha = models.CharField(max_length=64, blank=True)
    last_plugin_update_at = models.DateTimeField(null=True, blank=True)
    last_gitlab_update_at = models.DateTimeField(null=True, blank=True)
    sync_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("integration", "file_path")
        unique_together = (("integration", "device"), ("integration", "file_path"))
        verbose_name = "GitLab config mapping"
        verbose_name_plural = "GitLab config mappings"

    def __str__(self) -> str:
        return f"{self.device} -> {self.file_path}"

    def get_absolute_url(self):
        return reverse("plugins:main:gitlabconfigmapping", kwargs={"pk": self.pk})


class GitLabSyncLog(NetBoxModel):
    class Direction(models.TextChoices):
        GITLAB_TO_PLUGIN = "gitlab_to_plugin", "GitLab to plugin"
        PLUGIN_TO_GITLAB = "plugin_to_gitlab", "Plugin to GitLab"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"
        CONFLICT = "conflict", "Conflict"

    DIRECTION_GITLAB_TO_PLUGIN = Direction.GITLAB_TO_PLUGIN.value
    DIRECTION_PLUGIN_TO_GITLAB = Direction.PLUGIN_TO_GITLAB.value
    DIRECTION_CHOICES = Direction.choices
    STATUS_SUCCESS = Status.SUCCESS.value
    STATUS_FAILED = Status.FAILED.value
    STATUS_SKIPPED = Status.SKIPPED.value
    STATUS_CONFLICT = Status.CONFLICT.value
    STATUS_CHOICES = Status.choices

    integration = models.ForeignKey(
        GitLabIntegration,
        on_delete=models.CASCADE,
        related_name="sync_logs",
    )
    mapping = models.ForeignKey(
        GitLabConfigMapping,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_logs",
    )
    device = models.ForeignKey(
        "dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gitlab_sync_logs",
    )
    configuration_backup = models.ForeignKey(
        ConfigurationBackup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gitlab_sync_logs",
    )
    task = models.ForeignKey(
        "ScheduledTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gitlab_sync_logs",
    )
    direction = models.CharField(max_length=32, choices=Direction.choices)
    file_path = models.CharField(max_length=1024, blank=True)
    commit_sha = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    message = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = "GitLab sync log"
        verbose_name_plural = "GitLab sync logs"

    def __str__(self) -> str:
        return f"{self.integration} {self.direction} {self.status}"

    def get_absolute_url(self):
        return reverse("plugins:main:gitlabsynclog", kwargs={"pk": self.pk})


class ParameterSyncLog(NetBoxModel):
    class Direction(models.TextChoices):
        NETBOX_TO_CONFIG = "netbox_to_config", "NetBox to config"
        CONFIG_TO_NETBOX = "config_to_netbox", "Config to NetBox"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    DIRECTION_NETBOX_TO_CONFIG = Direction.NETBOX_TO_CONFIG.value
    DIRECTION_CONFIG_TO_NETBOX = Direction.CONFIG_TO_NETBOX.value
    DIRECTION_CHOICES = Direction.choices
    STATUS_SUCCESS = Status.SUCCESS.value
    STATUS_FAILED = Status.FAILED.value
    STATUS_SKIPPED = Status.SKIPPED.value
    STATUS_CHOICES = Status.choices

    device = models.ForeignKey("dcim.Device", on_delete=models.CASCADE, related_name="parameter_sync_logs")
    configuration_backup = models.ForeignKey(
        ConfigurationBackup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parameter_sync_logs",
    )
    direction = models.CharField(max_length=32, choices=Direction.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    origin = models.CharField(max_length=64, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True)
    message = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = "Parameter sync log"
        verbose_name_plural = "Parameter sync logs"

    def __str__(self) -> str:
        return f"{self.device} {self.direction} {self.status}"

    def get_absolute_url(self):
        return ""


class CredentialRevealAudit(NetBoxModel):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        BLOCKED = "blocked", "Blocked"

    credential = models.ForeignKey(
        DeviceCredential,
        on_delete=models.CASCADE,
        related_name="reveal_audits",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="config_weaver_credential_reveal_audits",
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    reason = models.CharField(max_length=128, blank=True)
    source_ip = models.GenericIPAddressField(protocol="IPv4", null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created",)
        verbose_name = "Credential reveal audit"
        verbose_name_plural = "Credential reveal audits"

    def __str__(self) -> str:
        return f"{self.credential} {self.status} {self.created}"

    def get_absolute_url(self):
        return ""


class DevicePlatformProfile(NetBoxModel):
    class Vendor(models.TextChoices):
        CISCO = "cisco", "Cisco"
        DLINK = "dlink", "D-Link"

    class Platform(models.TextChoices):
        CISCO_IOS = "cisco_ios", "Cisco IOS"
        CISCO_XE = "cisco_xe", "Cisco IOS-XE"
        CISCO_NXOS = "cisco_nxos", "Cisco NX-OS"
        DLINK_DS = "dlink_ds", "D-Link DS"
        DLINK_DGS = "dlink_dgs", "D-Link DGS"

    VENDOR_CISCO = Vendor.CISCO.value
    VENDOR_DLINK = Vendor.DLINK.value
    VENDOR_CHOICES = Vendor.choices
    PLATFORM_CISCO_IOS = Platform.CISCO_IOS.value
    PLATFORM_CISCO_XE = Platform.CISCO_XE.value
    PLATFORM_CISCO_NXOS = Platform.CISCO_NXOS.value
    PLATFORM_DLINK_DS = Platform.DLINK_DS.value
    PLATFORM_DLINK_DGS = Platform.DLINK_DGS.value
    PLATFORM_CHOICES = Platform.choices

    device = models.OneToOneField("dcim.Device", on_delete=models.CASCADE, related_name="config_weaver_profile")
    credential = models.ForeignKey(DeviceCredential, on_delete=models.PROTECT, related_name="device_profiles")
    vendor = models.CharField(max_length=16, choices=Vendor.choices)
    platform = models.CharField(max_length=32, choices=Platform.choices)
    management_ip = models.GenericIPAddressField(protocol="IPv4", null=True, blank=True)
    command_timeout = models.PositiveIntegerField(default=60)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("device",)
        verbose_name = "Device profile"
        verbose_name_plural = "Device profiles"

    def __str__(self) -> str:
        return str(self.device)

    def get_absolute_url(self):
        return reverse("plugins:main:deviceplatformprofile", kwargs={"pk": self.pk})

    def clean(self):
        vendor_platform = {
            self.VENDOR_CISCO: {
                self.PLATFORM_CISCO_IOS,
                self.PLATFORM_CISCO_XE,
                self.PLATFORM_CISCO_NXOS,
            },
            self.VENDOR_DLINK: {
                self.PLATFORM_DLINK_DS,
                self.PLATFORM_DLINK_DGS,
            },
        }
        if self.platform not in vendor_platform.get(self.vendor, set()):
            raise ValidationError("Platform does not match selected vendor.")


class ScheduledTask(NetBoxModel):
    class TaskType(models.TextChoices):
        APPLY_SCENARIO = "apply_scenario", "Apply scenario"
        BACKUP = "backup", "Save configuration"
        HEALTHCHECK = "healthcheck", "Check connectivity"

    class TaskStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    TYPE_APPLY_SCENARIO = TaskType.APPLY_SCENARIO.value
    TYPE_BACKUP = TaskType.BACKUP.value
    TYPE_HEALTHCHECK = TaskType.HEALTHCHECK.value
    TYPE_CHOICES = TaskType.choices
    STATUS_PENDING = TaskStatus.PENDING.value
    STATUS_RUNNING = TaskStatus.RUNNING.value
    STATUS_SUCCESS = TaskStatus.SUCCESS.value
    STATUS_FAILED = TaskStatus.FAILED.value
    STATUS_CHOICES = TaskStatus.choices

    task_name = models.CharField(max_length=150)
    task_type = models.CharField(max_length=40, choices=TaskType.choices)
    target_device = models.ForeignKey("dcim.Device", on_delete=models.CASCADE, related_name="scheduled_tasks")
    task = models.TextField(blank=True, verbose_name="Task (YAML)")
    schedule_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.PENDING.value)
    result_message = models.TextField(blank=True)
    run_every_seconds = models.PositiveIntegerField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    max_retries = models.PositiveIntegerField(default=0)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("schedule_time",)
        verbose_name = "Scheduled task"
        verbose_name_plural = "Scheduled tasks"

    def __str__(self) -> str:
        return self.task_name

    def get_absolute_url(self):
        return reverse("plugins:main:scheduledtask", kwargs={"pk": self.pk})

    def is_due(self) -> bool:
        if self.status == self.STATUS_PENDING:
            return self.schedule_time <= timezone.now()
        if self.status == self.STATUS_SUCCESS and self.run_every_seconds:
            return self.schedule_time <= timezone.now()
        return False

    def update_status(self, status: str, message: str = "") -> None:
        self.status = status
        self.result_message = message
        if status in {self.STATUS_SUCCESS, self.STATUS_FAILED}:
            self.last_run_at = timezone.now()
        self.save(update_fields=("status", "result_message", "last_run_at", "last_updated"))


class UMLConfiguration(NetBoxModel):
    class DiagramType(models.TextChoices):
        PLANTUML = "plantuml", "PlantUML"
        MERMAID = "mermaid", "Mermaid"
        JSON = "json", "JSON"

    TYPE_PLANTUML = DiagramType.PLANTUML.value
    TYPE_MERMAID = DiagramType.MERMAID.value
    TYPE_JSON = DiagramType.JSON.value
    TYPE_CHOICES = DiagramType.choices

    name = models.CharField(max_length=150)
    diagram_type = models.CharField(max_length=16, choices=DiagramType.choices, default=DiagramType.PLANTUML.value)
    task = models.ForeignKey(
        NetworkTask, on_delete=models.CASCADE, related_name="uml_configurations", null=True, blank=True
    )
    device = models.ForeignKey("dcim.Device", on_delete=models.CASCADE, related_name="uml_configurations", null=True, blank=True)
    source_text = models.TextField()
    rendered_svg = models.TextField(blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    revision = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "-revision")
        unique_together = ("name", "revision")
        verbose_name = "UML definition"
        verbose_name_plural = "UML definitions"

    def __str__(self) -> str:
        return f"{self.name} r{self.revision}"

    def get_absolute_url(self):
        return reverse("plugins:main:umlconfiguration", kwargs={"pk": self.pk})
