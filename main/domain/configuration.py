from __future__ import annotations
from typing import Any

import yaml

from ..models import CommandTemplate, DevicePlatformProfile


class ConfigValidationError(Exception):
    pass


class NetworkPlanParser:
    INTERFACE_ALIASES = {
        "gi": "GigabitEthernet",
        "fa": "FastEthernet",
        "te": "TenGigabitEthernet",
        "eth": "Ethernet",
        "po": "Port-channel",
    }

    @staticmethod
    def parse_plan(raw_yaml: str) -> dict[str, Any]:
        data = yaml.safe_load(raw_yaml) or {}
        if not isinstance(data, dict):
            raise ConfigValidationError("Network plan must be a YAML mapping")
        return data

    @classmethod
    def normalize_interfaces(cls, config: dict[str, Any]) -> dict[str, Any]:
        interfaces = config.get("interfaces", [])
        if not isinstance(interfaces, list):
            raise ConfigValidationError("'interfaces' must be a list")
        for item in interfaces:
            if not isinstance(item, dict):
                raise ConfigValidationError("Each interface item must be a mapping")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ConfigValidationError("Interface name is required")
            lower = name.lower()
            for short, full in cls.INTERFACE_ALIASES.items():
                if lower.startswith(short):
                    item["name"] = full + name[len(short) :]
                    break
        return config


class CommandGenerator:
    @staticmethod
    def split_rendered_commands(rendered: str) -> list[str]:
        return [line.strip() for line in rendered.splitlines() if line.strip()]

    @staticmethod
    def generate_interface_config(interface: dict[str, Any]) -> list[str]:
        commands = [f"interface {interface['name']}"]
        if interface.get("description"):
            commands.append(f"description {interface['description']}")
        commands.append("shutdown" if interface.get("shutdown") else "no shutdown")
        if interface.get("ip") and interface.get("mask"):
            commands.append(f"ip address {interface['ip']} {interface['mask']}")
        return commands

    @staticmethod
    def _resolve_template_key(
        operation: dict[str, Any],
        profile: DevicePlatformProfile,
    ) -> tuple[str, str, str, str | None]:
        vendor = str(operation.get("vendor") or profile.vendor).lower()
        platform = str(operation.get("platform") or profile.platform).lower()
        op_type = str(operation.get("operation_type") or CommandTemplate.OP_CUSTOM).lower()
        name = operation.get("name")
        return vendor, platform, op_type, str(name).lower() if name else None

    @classmethod
    def _append_raw_commands(cls, commands: list[str], raw_commands: Any) -> None:
        if raw_commands is None:
            return
        if isinstance(raw_commands, str):
            commands.extend(cls.split_rendered_commands(raw_commands))
            return
        if isinstance(raw_commands, list):
            for command in raw_commands:
                if not isinstance(command, str):
                    raise ConfigValidationError("Each raw command must be a string")
                commands.extend(cls.split_rendered_commands(command))
            return
        raise ConfigValidationError("'raw_commands' must be a string or a list of strings")

    @classmethod
    def generate_commands(
        cls,
        plan: dict[str, Any],
        templates: list[Any],
        profile: DevicePlatformProfile,
    ) -> list[str]:
        commands: list[str] = []
        for interface in plan.get("interfaces", []):
            commands.extend(cls.generate_interface_config(interface))

        template_index = {
            (t.vendor.lower(), t.platform.lower(), t.operation_type.lower(), t.name.lower()): t
            for t in templates
        }
        legacy_index = {
            (t.vendor.lower(), t.platform.lower(), t.operation_type.lower()): t
            for t in templates
            if not hasattr(t, "source")
        }

        for operation in plan.get("operations", []):
            if not isinstance(operation, dict):
                raise ConfigValidationError("Each operation must be a mapping")
            cls._append_raw_commands(commands, operation.get("raw_commands"))

            vendor, platform, op_type, name = cls._resolve_template_key(operation, profile)
            template = template_index.get((vendor, platform, op_type, name)) if name else None
            if template is None and name:
                same_platform = [
                    t for key, t in template_index.items()
                    if key[0] == vendor and key[1] == platform and key[3] == name
                ]
                same_vendor = [
                    t for key, t in template_index.items()
                    if key[0] == vendor and key[3] == name
                ]
                template = same_platform[0] if same_platform else same_vendor[0] if len(same_vendor) == 1 else None
            if template is None and not name:
                template = legacy_index.get((vendor, platform, op_type))
                if template is None:
                    same_vendor = [
                        t for key, t in legacy_index.items()
                        if key[0] == vendor and key[2] == op_type
                    ]
                    template = same_vendor[0] if len(same_vendor) == 1 else None
            if not template:
                if operation.get("raw_commands"):
                    continue
                template_ref = name or op_type
                raise ConfigValidationError(f"No command template for {vendor}/{platform}: {template_ref}")
            try:
                commands.extend(cls.split_rendered_commands(template.render(operation.get("params", {}))))
            except KeyError as exc:
                raise ConfigValidationError(f"Template '{template.name}' misses required param: {exc}") from exc
        cls._append_raw_commands(commands, plan.get("raw_commands"))
        return commands


class ConfigurationValidator:
    FORBIDDEN_PATTERNS = (
        "write erase",
        "erase startup-config",
        "delete flash:",
        "no username",
        "reload",
        "format flash",
    )

    @classmethod
    def validate_commands(cls, commands: list[str]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not commands:
            errors.append("No commands generated")
        if any(not cmd.strip() for cmd in commands):
            errors.append("Command list contains empty command")
        forbidden = [c for c in commands if any(p in c.strip().lower() for p in cls.FORBIDDEN_PATTERNS)]
        if forbidden:
            errors.append(f"Forbidden commands found: {forbidden}")
        return len(errors) == 0, errors
