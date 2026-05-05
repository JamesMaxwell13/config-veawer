from __future__ import annotations

from typing import Any

from ..domain.security import redact_secrets
from ..domain.terminal import TerminalBootstrapPolicy
from ..infrastructure.network import ConnectionSession
from ..infrastructure.terminal import ParamikoTerminalTransport
from ..infrastructure.vcs import ConfigurationVCS
from ..logging import device_log_context, logger
from ..models import DevicePlatformProfile


class DeviceTerminalError(Exception):
    pass


class DeviceTerminalService:
    def __init__(
        self,
        profile: DevicePlatformProfile,
        user: Any,
        transport: ParamikoTerminalTransport | None = None,
    ) -> None:
        self.profile = profile
        self.device = profile.device
        self.user = user
        self.host = self.resolve_host(profile)
        self.transport = transport or ParamikoTerminalTransport()
        self.closed = True

    @staticmethod
    def resolve_host(profile: DevicePlatformProfile) -> str:
        if profile.management_ip:
            return str(profile.management_ip)
        if profile.device.primary_ip4:
            return str(profile.device.primary_ip4.address).split("/")[0]
        raise DeviceTerminalError(f"Device {profile.device.name} has no management IP")

    def open(self) -> str:
        logger.info(
            "Opening manual terminal session %s user=%s",
            device_log_context(self.device, self.profile, self.host),
            self.user,
        )
        self.transport.open(self.host, self.profile.credential)
        self.closed = False
        for command in TerminalBootstrapPolicy.enter_config_mode(self.profile):
            self.transport.send_line(command)
        output = self.read_until_idle()
        logger.info(
            "Manual terminal session opened %s initial_output_length=%s user=%s",
            device_log_context(self.device, self.profile, self.host),
            len(output),
            self.user,
        )
        return output

    def send_input(self, data: str) -> None:
        if self.closed:
            raise DeviceTerminalError("Terminal session is closed")
        self.transport.send(data)
        logger.info(
            "Manual terminal input sent %s input_length=%s user=%s",
            device_log_context(self.device, self.profile, self.host),
            len(redact_secrets(data)),
            self.user,
        )

    def read_available(self) -> str:
        if self.closed:
            return ""
        output = self.transport.read_available()
        if output:
            logger.info(
                "Manual terminal output received %s output_length=%s user=%s",
                device_log_context(self.device, self.profile, self.host),
                len(output),
                self.user,
            )
        return output

    def read_until_idle(self, idle_seconds: float = 0.25, max_seconds: float = 3.0) -> str:
        if self.closed:
            return ""
        return self.transport.read_until_idle(idle_seconds=idle_seconds, max_seconds=max_seconds)

    def close(self, create_backup: bool = True) -> None:
        if self.closed:
            return
        try:
            if create_backup:
                self._create_backup()
        finally:
            self.closed = True
            try:
                self.transport.close()
            except Exception:
                logger.exception(
                    "Failed to close terminal transport %s user=%s",
                    device_log_context(self.device, self.profile, self.host),
                    self.user,
                )
            logger.info(
                "Manual terminal session closed %s user=%s",
                device_log_context(self.device, self.profile, self.host),
                self.user,
            )

    def _create_backup(self) -> None:
        try:
            for command in TerminalBootstrapPolicy.leave_config_mode(self.profile):
                self.transport.send_line(command)
            self.read_until_idle(idle_seconds=0.2, max_seconds=1.0)
            command = ConnectionSession.RUNNING_CONFIG_COMMANDS.get(self.profile.platform)
            if not command:
                logger.warning(
                    "Skipping terminal backup for unsupported platform %s",
                    device_log_context(self.device, self.profile, self.host),
                )
                return
            config = self.transport.read_command(command)
            backup = ConfigurationVCS.write_backup(
                self.device,
                config,
                source="terminal_session",
            )
            logger.info(
                "Manual terminal backup created %s backup_id=%s version=%s user=%s",
                device_log_context(self.device, self.profile, self.host),
                backup.pk,
                backup.version,
                self.user,
            )
        except Exception:
            logger.exception(
                "Manual terminal backup failed %s user=%s",
                device_log_context(self.device, self.profile, self.host),
                self.user,
            )
