from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import hashlib
import re

import yaml
from django.utils import timezone

from ..domain.configuration import CommandGenerator, ConfigValidationError
from ..domain.security import redact_secrets
from ..infrastructure.repositories import ConfigurationRepository
from ..models import DevicePlatformProfile


class _ConfigurationYAMLDumper(yaml.SafeDumper):
    pass


def _represent_multiline_string(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_ConfigurationYAMLDumper.add_representer(str, _represent_multiline_string)


@dataclass(frozen=True)
class _CompiledTemplate:
    template: Any
    line_patterns: tuple[re.Pattern, ...]
    params: tuple[str, ...]


class ConfigurationYamlService:
    SCHEMA_VERSION = 1

    @staticmethod
    def dump_yaml(payload: dict[str, Any]) -> str:
        return yaml.dump(
            payload,
            Dumper=_ConfigurationYAMLDumper,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    @classmethod
    def is_yaml_config(cls, value: str) -> bool:
        try:
            data = yaml.safe_load(value) or {}
        except yaml.YAMLError:
            return False
        return isinstance(data, dict) and data.get("schema_version") == cls.SCHEMA_VERSION

    @classmethod
    def checksum(cls, yaml_text: str) -> str:
        return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_line(line: str) -> str:
        return re.sub(r"\s+", " ", line.strip())

    @classmethod
    def _config_lines(cls, raw_config: str) -> list[str]:
        ignored_prefixes = (
            "building configuration",
            "current configuration",
            "end",
        )
        lines: list[str] = []
        for line in raw_config.splitlines():
            normalized = cls._normalize_line(line)
            if not normalized or normalized == "!":
                continue
            if any(normalized.lower().startswith(prefix) for prefix in ignored_prefixes):
                continue
            lines.append(normalized)
        return lines

    @classmethod
    def _line_pattern(cls, template_line: str) -> tuple[re.Pattern, tuple[str, ...]]:
        params: list[str] = []
        pattern = ""
        cursor = 0
        seen: set[str] = set()
        for match in re.finditer(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", template_line):
            pattern += re.escape(template_line[cursor:match.start()])
            name = match.group(1)
            params.append(name)
            if name in seen:
                pattern += rf"(?P={name})"
            else:
                pattern += rf"(?P<{name}>.+?)"
                seen.add(name)
            cursor = match.end()
        pattern += re.escape(template_line[cursor:])
        return re.compile(rf"^{pattern}$"), tuple(params)

    @classmethod
    def _compile_templates(cls, profile: DevicePlatformProfile | None) -> list[_CompiledTemplate]:
        compiled: list[_CompiledTemplate] = []
        for template in ConfigurationRepository.active_templates():
            if profile and (
                template.vendor.lower() != profile.vendor.lower()
                or template.platform.lower() != profile.platform.lower()
            ):
                continue
            raw_lines = [
                cls._normalize_line(line)
                for line in str(template.command_body).splitlines()
                if cls._normalize_line(line)
            ]
            if not raw_lines:
                continue
            line_patterns = []
            params: list[str] = []
            for raw_line in raw_lines:
                pattern, line_params = cls._line_pattern(raw_line)
                line_patterns.append(pattern)
                params.extend(line_params)
            compiled.append(_CompiledTemplate(template, tuple(line_patterns), tuple(dict.fromkeys(params))))
        return sorted(compiled, key=lambda item: len(item.line_patterns), reverse=True)

    @classmethod
    def _match_template(
        cls,
        lines: list[str],
        offset: int,
        template: _CompiledTemplate,
    ) -> dict[str, str] | None:
        if offset + len(template.line_patterns) > len(lines):
            return None
        params: dict[str, str] = {}
        for index, pattern in enumerate(template.line_patterns):
            match = pattern.fullmatch(lines[offset + index])
            if not match:
                return None
            for key, value in match.groupdict().items():
                if key in params and params[key] != value:
                    return None
                params[key] = value
        return params

    @classmethod
    def running_config_to_payload(
        cls,
        device,
        raw_config: str,
        source: str = "runtime",
    ) -> dict[str, Any]:
        profile = DevicePlatformProfile.objects.filter(device=device, enabled=True).first()
        lines = cls._config_lines(redact_secrets(raw_config))
        templates = cls._compile_templates(profile)
        operations: list[dict[str, Any]] = []
        raw_commands: list[str] = []

        index = 0
        while index < len(lines):
            matched = False
            for template in templates:
                params = cls._match_template(lines, index, template)
                if params is None:
                    continue
                operations.append(
                    {
                        "name": template.template.name,
                        "operation_type": template.template.operation_type,
                        "params": params,
                    }
                )
                index += len(template.line_patterns)
                matched = True
                break
            if not matched:
                raw_commands.append(lines[index])
                index += 1

        return {
            "schema_version": cls.SCHEMA_VERSION,
            "device": {
                "id": device.pk,
                "name": device.name,
            },
            "platform": profile.platform if profile else None,
            "source": source,
            "saved_at": timezone.now().isoformat(),
            "operations": operations,
            "raw_commands": raw_commands,
        }

    @classmethod
    def running_config_to_yaml(cls, device, raw_config: str, source: str = "runtime") -> str:
        return cls.dump_yaml(cls.running_config_to_payload(device, raw_config, source=source))

    @classmethod
    def load_payload(cls, yaml_text: str) -> dict[str, Any]:
        try:
            data = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError as exc:
            raise ConfigValidationError(f"Invalid configuration YAML: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema_version") != cls.SCHEMA_VERSION:
            raise ConfigValidationError("Unsupported configuration YAML schema")
        return data

    @classmethod
    def yaml_to_commands(cls, yaml_text: str, profile: DevicePlatformProfile) -> list[str]:
        if not cls.is_yaml_config(yaml_text):
            return [
                line.strip()
                for line in yaml_text.splitlines()
                if line.strip() and not line.strip().startswith("!")
            ]
        payload = cls.load_payload(yaml_text)
        plan = {
            "operations": payload.get("operations") or [],
            "raw_commands": payload.get("raw_commands") or [],
        }
        return CommandGenerator.generate_commands(
            plan,
            ConfigurationRepository.active_templates(),
            profile,
        )
