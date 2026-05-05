from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("netbox.plugins.config_weaver")


def device_log_context(device: Any, profile: Any | None = None, host: str | None = None) -> str:
    device_name = getattr(device, "name", str(device))
    device_id = getattr(device, "pk", None)
    if host is None and profile is not None:
        management_ip = getattr(profile, "management_ip", None)
        host = str(management_ip) if management_ip else None
    if host is None:
        primary_ip4 = getattr(device, "primary_ip4", None)
        address = getattr(primary_ip4, "address", None)
        host = str(address).split("/")[0] if address else None

    parts = [f"device={device_name}"]
    if device_id is not None:
        parts.append(f"device_id={device_id}")
    if host:
        parts.append(f"ip={host}")
    if profile is not None:
        profile_id = getattr(profile, "pk", None)
        platform = getattr(profile, "platform", None)
        if profile_id is not None:
            parts.append(f"profile_id={profile_id}")
        if platform:
            parts.append(f"platform={platform}")
    return " ".join(parts)


def task_log_context(task: Any) -> str:
    parts = [
        f"task={getattr(task, 'task_name', task)}",
        f"task_id={getattr(task, 'pk', None)}",
        f"type={getattr(task, 'task_type', None)}",
    ]
    device = getattr(task, "target_device", None)
    if device is not None:
        parts.append(device_log_context(device))
    return " ".join(part for part in parts if not part.endswith("=None"))
