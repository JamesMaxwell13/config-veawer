from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from netbox.models import NetBoxModel

from .crypto import decrypt_value, encrypt_value, is_encrypted


class DeviceCredential(NetBoxModel):
    AUTH_PASSWORD = "password"
    AUTH_CHOICES = (
        (AUTH_PASSWORD, "Username/Password"),
    )

    name = models.CharField(max_length=100, unique=True)
    auth_method = models.CharField(max_length=32, choices=AUTH_CHOICES, default=AUTH_PASSWORD)
    username = models.CharField(max_length=128)
    password = models.CharField(max_length=255)
    enable_secret = models.CharField(max_length=255, blank=True)
    ssh_port = models.PositiveIntegerField(default=22)
    timeout = models.PositiveIntegerField(default=30)
    use_enable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

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


class CommandTemplate(NetBoxModel):
    OP_INTERFACE = "interface"
    OP_VLAN = "vlan"
    OP_IP = "ip"
    OP_CUSTOM = "custom"
    OP_CHOICES = (
        (OP_INTERFACE, "Interface config"),
        (OP_VLAN, "VLAN config"),
        (OP_IP, "IP config"),
        (OP_CUSTOM, "Custom"),
    )

    name = models.CharField(max_length=100)
    vendor = models.CharField(max_length=100)
    platform = models.CharField(max_length=100)
    operation_type = models.CharField(max_length=32, choices=OP_CHOICES, default=OP_CUSTOM)
    command_body = models.TextField()
    is_active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("vendor", "platform", "operation_type", "name")
        unique_together = ("name", "vendor", "platform", "operation_type")

    def __str__(self) -> str:
        return f"{self.name} ({self.vendor}/{self.platform})"

    def render(self, params: dict) -> str:
        return self.command_body.format(**params)


class NetworkTask(NetBoxModel):
    PLAN_YAML = "yaml"
    PLAN_CHOICES = ((PLAN_YAML, "YAML"),)

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    device_task = models.CharField(max_length=255)
    plan_format = models.CharField(max_length=16, choices=PLAN_CHOICES, default=PLAN_YAML)
    plan_yaml = models.TextField()
    plan_checksum = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField(default=True)
    last_validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

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

    def __str__(self) -> str:
        return f"{self.device} v{self.version}"


class DevicePlatformProfile(NetBoxModel):
    VENDOR_CISCO = "cisco"
    VENDOR_DLINK = "dlink"
    VENDOR_CHOICES = (
        (VENDOR_CISCO, "Cisco"),
        (VENDOR_DLINK, "D-Link"),
    )

    PLATFORM_CISCO_IOS = "cisco_ios"
    PLATFORM_CISCO_XE = "cisco_xe"
    PLATFORM_CISCO_NXOS = "cisco_nxos"
    PLATFORM_DLINK_DS = "dlink_ds"
    PLATFORM_DLINK_DGS = "dlink_dgs"
    PLATFORM_CHOICES = (
        (PLATFORM_CISCO_IOS, "Cisco IOS"),
        (PLATFORM_CISCO_XE, "Cisco IOS-XE"),
        (PLATFORM_CISCO_NXOS, "Cisco NX-OS"),
        (PLATFORM_DLINK_DS, "D-Link DS"),
        (PLATFORM_DLINK_DGS, "D-Link DGS"),
    )

    device = models.OneToOneField("dcim.Device", on_delete=models.CASCADE, related_name="config_weaver_profile")
    credential = models.ForeignKey(DeviceCredential, on_delete=models.PROTECT, related_name="device_profiles")
    vendor = models.CharField(max_length=16, choices=VENDOR_CHOICES)
    platform = models.CharField(max_length=32, choices=PLATFORM_CHOICES)
    management_ip = models.GenericIPAddressField(protocol="IPv4", null=True, blank=True)
    command_timeout = models.PositiveIntegerField(default=60)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("device",)

    def __str__(self) -> str:
        return f"{self.device} ({self.vendor}/{self.platform})"

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
    TYPE_APPLY_SCENARIO = "apply_scenario"
    TYPE_BACKUP = "backup"
    TYPE_HEALTHCHECK = "healthcheck"
    TYPE_CHOICES = (
        (TYPE_APPLY_SCENARIO, "Apply scenario"),
        (TYPE_BACKUP, "Create backup"),
        (TYPE_HEALTHCHECK, "Health check"),
    )

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    )

    task_name = models.CharField(max_length=150)
    task_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    target_device = models.ForeignKey("dcim.Device", on_delete=models.CASCADE, related_name="scheduled_tasks")
    task = models.ForeignKey(
        NetworkTask, on_delete=models.SET_NULL, null=True, blank=True, related_name="scheduled_tasks"
    )
    schedule_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    result_message = models.TextField(blank=True)
    run_every_seconds = models.PositiveIntegerField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    max_retries = models.PositiveIntegerField(default=0)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("schedule_time",)

    def __str__(self) -> str:
        return self.task_name

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
    TYPE_PLANTUML = "plantuml"
    TYPE_MERMAID = "mermaid"
    TYPE_JSON = "json"
    TYPE_CHOICES = (
        (TYPE_PLANTUML, "PlantUML"),
        (TYPE_MERMAID, "Mermaid"),
        (TYPE_JSON, "JSON"),
    )

    name = models.CharField(max_length=150)
    diagram_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_PLANTUML)
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

    def __str__(self) -> str:
        return f"{self.name} r{self.revision}"
