from __future__ import annotations

from dcim.models import Device

from ..application.configuration_yaml import ConfigurationYamlService
from ..domain.configuration import ConfigValidationError, ConfigurationValidator
from ..models import DevicePlatformProfile


def _plain_text_commands(config_text: str) -> list[str]:
    return [
        line.strip()
        for line in str(config_text).splitlines()
        if line.strip() and not line.strip().startswith("!")
    ]


def _commands_from_yaml_without_profile(yaml_text: str) -> list[str]:
    payload = ConfigurationYamlService.load_payload(yaml_text)
    operations = list(payload.get("operations") or [])
    sections = list(payload.get("sections") or [])
    has_section_operations = any(section.get("operations") for section in sections if isinstance(section, dict))
    if operations or has_section_operations:
        raise ConfigValidationError(
            "Active device profile is required to validate templated YAML operations."
        )

    commands: list[str] = []
    commands.extend(payload.get("raw_commands") or [])
    for section in sections:
        if not isinstance(section, dict):
            continue
        header = str(section.get("header") or "").strip()
        if header:
            commands.append(header)
        commands.extend(section.get("raw_commands") or [])
    return commands


class ConfigurationInputValidator:
    @classmethod
    def commands_for_validation(cls, *, device: Device, config_text: str) -> list[str]:
        profile = DevicePlatformProfile.objects.filter(device=device, enabled=True).first()
        if profile:
            if ConfigurationYamlService.is_yaml_config(config_text):
                return ConfigurationYamlService.yaml_to_commands(config_text, profile)
            return _plain_text_commands(config_text)

        if ConfigurationYamlService.is_yaml_config(config_text):
            return _commands_from_yaml_without_profile(config_text)
        return _plain_text_commands(config_text)

    @classmethod
    def validate_backup_input_or_raise(cls, *, device: Device, config_text: str) -> None:
        commands = cls.commands_for_validation(device=device, config_text=config_text)
        valid, errors = ConfigurationValidator.validate_commands(commands)
        if not valid:
            raise ConfigValidationError("; ".join(errors))
