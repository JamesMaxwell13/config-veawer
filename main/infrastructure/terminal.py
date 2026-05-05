from __future__ import annotations

import time
from typing import Any

import paramiko

from ..models import DeviceCredential


class TerminalTransportError(Exception):
    pass


class ParamikoTerminalTransport:
    def __init__(self) -> None:
        self.client: paramiko.SSHClient | None = None
        self.shell: Any = None
        self.closed = True

    def open(self, host: str, credential: DeviceCredential) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            port=credential.ssh_port,
            username=credential.username,
            password=credential.password_plain,
            timeout=credential.timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        self.client = client
        self.shell = client.invoke_shell(width=200, height=1000)
        self.closed = False

    def send(self, data: str) -> None:
        if self.closed or not self.shell:
            raise TerminalTransportError("Terminal transport is closed")
        self.shell.send(data)

    def send_line(self, command: str) -> None:
        self.send(f"{command}\n")

    def read_available(self) -> str:
        if self.closed or not self.shell:
            return ""
        chunks: list[str] = []
        while self.shell.recv_ready():
            chunks.append(self.shell.recv(65535).decode("utf-8", errors="replace"))
        return "".join(chunks)

    def read_until_idle(self, idle_seconds: float = 0.25, max_seconds: float = 3.0) -> str:
        output: list[str] = []
        deadline = time.monotonic() + max_seconds
        idle_deadline = time.monotonic() + idle_seconds
        while time.monotonic() < deadline:
            chunk = self.read_available()
            if chunk:
                output.append(chunk)
                idle_deadline = time.monotonic() + idle_seconds
            elif time.monotonic() >= idle_deadline:
                break
            time.sleep(0.05)
        return "".join(output)

    def read_command(self, command: str) -> str:
        if not self.client:
            raise TerminalTransportError("Terminal transport is closed")
        _stdin, stdout, _stderr = self.client.exec_command(command)
        return stdout.read().decode("utf-8", errors="replace")

    def close(self) -> None:
        self.closed = True
        if self.shell:
            self.shell.close()
        if self.client:
            self.client.close()
