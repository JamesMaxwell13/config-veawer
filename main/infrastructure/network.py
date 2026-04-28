from __future__ import annotations

from datetime import timedelta
from typing import Any

from dcim.models import Device
from django.core.cache import cache
from django.utils import timezone
from netmiko import ConnectHandler
import paramiko

from ..models import DeviceCredential, DevicePlatformProfile, ScheduledTask
from .repositories import ConfigurationRepository
from .vcs import ConfigurationVCS


class ConnectionSessionError(Exception):
    pass


class ConnectionSession:
    NETMIKO_DEVICE_MAP = {
        "cisco_ios": "cisco_ios",
        "cisco_xe": "cisco_xe",
        "cisco_nxos": "cisco_nxos",
        "dlink_ds": "dlink_ds",
        "dlink_dgs": "dlink_ds",
    }

    RUNNING_CONFIG_COMMANDS = {
        "cisco_ios": "show running-config",
        "cisco_xe": "show running-config",
        "cisco_nxos": "show running-config",
        "dlink_ds": "show running-config",
        "dlink_dgs": "show running-config",
    }

    SAVE_COMMANDS = {
        "cisco_ios": "write memory",
        "cisco_xe": "write memory",
        "cisco_nxos": "copy running-config startup-config",
        "dlink_ds": "save",
        "dlink_dgs": "save",
    }

    def __init__(self) -> None:
        self.session: Any = None
        self.backend: str | None = None
        self.platform: str | None = None

    def connect(self, host: str, platform: str, credential: DeviceCredential, prefer: str = "netmiko") -> Any:
        if platform not in self.NETMIKO_DEVICE_MAP:
            raise ConnectionSessionError(f"Unsupported platform: {platform}")
        self.platform = platform
        params = {
            "host": host,
            "username": credential.username,
            "password": credential.password_plain,
            "port": credential.ssh_port,
            "timeout": credential.timeout,
        }
        if prefer == "netmiko":
            try:
                return self._connect_netmiko(params, credential)
            except Exception:
                return self._connect_paramiko(params)
        return self._connect_paramiko(params)

    def _connect_netmiko(self, params: dict[str, Any], credential: DeviceCredential) -> Any:
        self.session = ConnectHandler(device_type=self.NETMIKO_DEVICE_MAP[self.platform or ""], **params)
        if credential.use_enable and credential.enable_secret_plain:
            self.session.secret = credential.enable_secret_plain
            self.session.enable()
        self.backend = "netmiko"
        return self.session

    def _connect_paramiko(self, params: dict[str, Any]) -> Any:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(**params)
        self.session = client
        self.backend = "paramiko"
        return self.session

    def disconnect(self) -> None:
        if not self.session:
            return
        if self.backend == "netmiko":
            self.session.disconnect()
        else:
            self.session.close()
        self.session = None

    def is_alive(self) -> bool:
        if not self.session:
            return False
        if self.backend == "netmiko":
            return bool(self.session.is_alive().get("is_alive"))
        transport = self.session.get_transport()
        return bool(transport and transport.is_active())

    def send_config_set(self, commands: list[str]) -> str:
        if not commands:
            return ""
        if self.backend == "netmiko":
            output = self.session.send_config_set(commands)
            output += f"\n{self.session.send_command_timing(self.SAVE_COMMANDS[self.platform or 'cisco_ios'])}"
            return output
        shell = self.session.invoke_shell()
        shell.send("configure terminal\n")
        for command in commands:
            shell.send(f"{command}\n")
        shell.send("end\n")
        shell.send(f"{self.SAVE_COMMANDS[self.platform or 'cisco_ios']}\n")
        return "Commands sent via Paramiko shell"

    def get_running_config(self) -> str:
        command = self.RUNNING_CONFIG_COMMANDS[self.platform or "cisco_ios"]
        if self.backend == "netmiko":
            return self.session.send_command(command)
        _stdin, stdout, _stderr = self.session.exec_command(command)
        return stdout.read().decode("utf-8", errors="ignore")


class DeviceConnectionManager:
    @staticmethod
    def get_profile(device: Device) -> DevicePlatformProfile | None:
        key = f"cw:profile:{device.pk}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        profile = DevicePlatformProfile.objects.filter(device=device, enabled=True).first()
        cache.set(key, profile, timeout=120)
        return profile

    @staticmethod
    def should_verify_saved_config(device: Device) -> bool:
        latest = ConfigurationRepository.latest_backup_for_device(device.pk)
        if latest is None:
            return True
        if latest.created and timezone.now() - latest.created >= timedelta(days=1):
            return True
        failed_healthcheck = ScheduledTask.objects.filter(
            target_device=device,
            task_type=ScheduledTask.TYPE_HEALTHCHECK,
            status=ScheduledTask.STATUS_FAILED,
        ).exists()
        return failed_healthcheck

    @staticmethod
    def verify_and_sync_running_config(device: Device, running_config: str) -> dict[str, Any]:
        latest = ConfigurationRepository.latest_backup_for_device(device.pk)
        if latest is None:
            backup = ConfigurationVCS.write_backup(device=device, config_text=running_config, source="integrity_check")
            return {"synced": False, "created_backup": backup.version, "reason": "no_backup"}

        incoming_checksum = __import__("hashlib").sha256(running_config.encode("utf-8")).hexdigest()
        if latest.config_checksum != incoming_checksum:
            backup = ConfigurationVCS.write_backup(device=device, config_text=running_config, source="integrity_check")
            return {"synced": False, "created_backup": backup.version, "reason": "drift_detected"}

        return {"synced": True, "created_backup": None, "reason": "up_to_date"}


def connect_device_cli(
    device: Device,
    prefer: str = "netmiko",
    verify_saved_config: bool = True,
) -> tuple[ConnectionSession, DevicePlatformProfile, dict[str, Any]]:
    profile = DeviceConnectionManager.get_profile(device)
    if not profile:
        raise ConnectionSessionError(f"No active device profile for {device.name}")

    host = str(profile.management_ip) if profile.management_ip else None
    if not host and profile.device.primary_ip4:
        host = str(profile.device.primary_ip4.address).split("/")[0]
    if not host:
        raise ConnectionSessionError(f"Device {device.name} has no management IP")

    session = ConnectionSession()
    session.connect(host, profile.platform, profile.credential, prefer=prefer)

    check_result = {"checked": False}
    if verify_saved_config and DeviceConnectionManager.should_verify_saved_config(device):
        running = session.get_running_config()
        check_result = DeviceConnectionManager.verify_and_sync_running_config(device, running)
        check_result["checked"] = True

    return session, profile, check_result
