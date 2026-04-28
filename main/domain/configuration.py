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
    def generate_interface_config(interface: dict[str, Any]) -> list[str]:
        commands = [f"interface {interface['name']}"]
        if interface.get("description"):
            commands.append(f"description {interface['description']}")
        commands.append("shutdown" if interface.get("shutdown") else "no shutdown")
        if interface.get("ip") and interface.get("mask"):
            commands.append(f"ip address {interface['ip']} {interface['mask']}")
        return commands

    @staticmethod
    def _resolve_template_key(operation: dict[str, Any], profile: DevicePlatformProfile) -> tuple[str, str, str]:
        vendor = str(operation.get("vendor") or profile.vendor).lower()
        platform = str(operation.get("platform") or profile.platform).lower()
        op_type = str(operation.get("operation_type") or CommandTemplate.OP_CUSTOM)
        return vendor, platform, op_type

    @classmethod
    def generate_commands(
        cls,
        plan: dict[str, Any],
        templates: list[CommandTemplate],
        profile: DevicePlatformProfile,
    ) -> list[str]:
        commands: list[str] = []
        for interface in plan.get("interfaces", []):
            commands.extend(cls.generate_interface_config(interface))
        template_index = {(t.vendor.lower(), t.platform.lower(), t.operation_type): t for t in templates}
        for operation in plan.get("operations", []):
            key = cls._resolve_template_key(operation, profile)
            template = template_index.get(key)
            if not template:
                continue
            try:
                commands.append(template.render(operation.get("params", {})))
            except KeyError as exc:
                raise ConfigValidationError(f"Template '{template.name}' misses required param: {exc}") from exc
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
