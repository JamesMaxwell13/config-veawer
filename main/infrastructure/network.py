from __future__ import annotations

from datetime import timedelta
from typing import Any

from dcim.models import Device
from django.core.cache import cache
from django.utils import timezone
from netmiko import ConnectHandler
import paramiko

from ..models import DeviceCredential, DevicePlatformProfile, ScheduledTask
from ..application.configuration_yaml import ConfigurationYamlService
from ..logging import device_log_context, logger
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

    @classmethod
    def save_command_for_platform(cls, platform: str | None) -> str:
        return cls.SAVE_COMMANDS[platform or "cisco_ios"]

    @classmethod
    def with_save_command(cls, commands: list[str], platform: str | None) -> list[str]:
        if not commands:
            return []
        save_command = cls.save_command_for_platform(platform)
        save_key = save_command.strip().lower()
        normalized = [command.strip() for command in commands if command.strip()]
        if any(command.lower() == save_key for command in normalized):
            return normalized
        return [*normalized, save_command]

    @classmethod
    def split_save_command(cls, commands: list[str], platform: str | None) -> tuple[list[str], str]:
        save_command = cls.save_command_for_platform(platform)
        save_key = save_command.strip().lower()
        commands_with_save = cls.with_save_command(commands, platform)
        config_commands = [command for command in commands_with_save if command.lower() != save_key]
        return config_commands, save_command

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
                logger.info("Connecting to device host=%s platform=%s backend=netmiko", host, platform)
                return self._connect_netmiko(params, credential)
            except Exception as exc:
                logger.warning(
                    "Netmiko connection failed; falling back to Paramiko host=%s platform=%s error=%s",
                    host,
                    platform,
                    exc,
                )
                return self._connect_paramiko(params)
        logger.info("Connecting to device host=%s platform=%s backend=paramiko", host, platform)
        return self._connect_paramiko(params)

    def _connect_netmiko(self, params: dict[str, Any], credential: DeviceCredential) -> Any:
        self.session = ConnectHandler(device_type=self.NETMIKO_DEVICE_MAP[self.platform or ""], **params)
        if credential.use_enable and credential.enable_secret_plain:
            self.session.secret = credential.enable_secret_plain
            self.session.enable()
        self.backend = "netmiko"
        logger.info("Device connection established host=%s platform=%s backend=netmiko", params["host"], self.platform)
        return self.session

    def _connect_paramiko(self, params: dict[str, Any]) -> Any:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_params = dict(params)
        connect_params["hostname"] = connect_params.pop("host")
        client.connect(**connect_params)
        self.session = client
        self.backend = "paramiko"
        logger.info(
            "Device connection established host=%s platform=%s backend=paramiko",
            params["host"],
            self.platform,
        )
        return self.session

    def disconnect(self) -> None:
        if not self.session:
            return
        backend = self.backend
        platform = self.platform
        if self.backend == "netmiko":
            self.session.disconnect()
        else:
            self.session.close()
        self.session = None
        logger.info("Device connection closed platform=%s backend=%s", platform, backend)

    def is_alive(self) -> bool:
        if not self.session:
            return False
        if self.backend == "netmiko":
            return bool(self.session.is_alive().get("is_alive"))
        transport = self.session.get_transport()
        return bool(transport and transport.is_active())

    def send_config_set(self, commands: list[str]) -> str:
        if not commands:
            logger.info("No configuration commands to send platform=%s backend=%s", self.platform, self.backend)
            return ""
        config_commands, save_command = self.split_save_command(commands, self.platform)
        command_count = len(config_commands) + 1
        logger.info(
            "Sending configuration commands command_count=%s platform=%s backend=%s",
            command_count,
            self.platform,
            self.backend,
        )
        if self.backend == "netmiko":
            output = self.session.send_config_set(config_commands) if config_commands else ""
            output += f"\n{self.session.send_command_timing(save_command)}"
            logger.info(
                "Configuration commands completed command_count=%s platform=%s backend=netmiko output_length=%s",
                command_count,
                self.platform,
                len(output),
            )
            return output
        shell = self.session.invoke_shell()
        if config_commands:
            shell.send("configure terminal\n")
            for command in config_commands:
                shell.send(f"{command}\n")
            shell.send("end\n")
        shell.send(f"{save_command}\n")
        logger.info(
            "Configuration commands completed command_count=%s platform=%s backend=paramiko",
            command_count,
            self.platform,
        )
        return "Commands sent via Paramiko shell"

    def get_running_config(self) -> str:
        command = self.RUNNING_CONFIG_COMMANDS[self.platform or "cisco_ios"]
        logger.info("Reading running configuration platform=%s backend=%s", self.platform, self.backend)
        if self.backend == "netmiko":
            config = self.session.send_command(command)
            logger.info(
                "Running configuration read platform=%s backend=netmiko config_length=%s",
                self.platform,
                len(config),
            )
            return config
        _stdin, stdout, _stderr = self.session.exec_command(command)
        config = stdout.read().decode("utf-8", errors="ignore")
        logger.info(
            "Running configuration read platform=%s backend=paramiko config_length=%s",
            self.platform,
            len(config),
        )
        return config


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

        incoming_yaml = ConfigurationYamlService.running_config_to_yaml(
            device,
            running_config,
            source="integrity_check",
        )
        incoming_checksum = ConfigurationYamlService.checksum(incoming_yaml)
        if latest.config_checksum != incoming_checksum:
            backup = ConfigurationVCS.write_backup(device=device, config_text=incoming_yaml, source="integrity_check")
            return {"synced": False, "created_backup": backup.version, "reason": "drift_detected"}

        return {"synced": True, "created_backup": None, "reason": "up_to_date"}


def connect_device_cli(
    device: Device,
    prefer: str = "netmiko",
    verify_saved_config: bool = True,
) -> tuple[ConnectionSession, DevicePlatformProfile, dict[str, Any]]:
    profile = DeviceConnectionManager.get_profile(device)
    if not profile:
        logger.warning("No active device profile %s", device_log_context(device))
        raise ConnectionSessionError(f"No active device profile for {device.name}")

    host = str(profile.management_ip) if profile.management_ip else None
    if not host and profile.device.primary_ip4:
        host = str(profile.device.primary_ip4.address).split("/")[0]
    if not host:
        logger.warning("Device has no management IP %s", device_log_context(device, profile))
        raise ConnectionSessionError(f"Device {device.name} has no management IP")

    session = ConnectionSession()
    logger.info(
        "Opening device CLI connection %s verify_saved_config=%s prefer=%s",
        device_log_context(device, profile, host),
        verify_saved_config,
        prefer,
    )
    try:
        session.connect(host, profile.platform, profile.credential, prefer=prefer)
    except Exception:
        logger.exception("Device CLI connection failed %s", device_log_context(device, profile, host))
        raise

    check_result = {"checked": False}
    if verify_saved_config and DeviceConnectionManager.should_verify_saved_config(device):
        logger.info("Verifying saved configuration %s", device_log_context(device, profile, host))
        running = session.get_running_config()
        check_result = DeviceConnectionManager.verify_and_sync_running_config(device, running)
        check_result["checked"] = True
        logger.info(
            "Saved configuration verification completed %s synced=%s created_backup=%s reason=%s",
            device_log_context(device, profile, host),
            check_result.get("synced"),
            check_result.get("created_backup"),
            check_result.get("reason"),
        )

    return session, profile, check_result
