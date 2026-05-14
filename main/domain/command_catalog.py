from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from ..models import CommandTemplate
from .configuration import ConfigValidationError


CATALOG_PACKAGE = "main.command_catalog"
CATALOG_FILES = ("cisco.yaml", "dlink.yaml")


@dataclass(frozen=True)
class CatalogCommandTemplate:
    name: str
    vendor: str
    platform: str
    operation_type: str
    command_body: str
    is_active: bool = True
    revision: int = 1
    description: str = ""
    params: tuple[str, ...] = ()
    source: str = "catalog"
    bound_entity_type: str = ""
    bound_parameter: str = ""
    bound_direction: str = "both"
    binding_priority: int = 100

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.vendor.lower(),
            self.platform.lower(),
            self.operation_type.lower(),
            self.name.lower(),
        )

    @property
    def legacy_key(self) -> tuple[str, str, str]:
        return self.key[:3]

    def render(self, params: dict[str, Any]) -> str:
        return self.command_body.format(**params)


def template_key(template: CommandTemplate | CatalogCommandTemplate) -> tuple[str, str, str, str]:
    return (
        template.vendor.lower(),
        template.platform.lower(),
        template.operation_type.lower(),
        template.name.lower(),
    )


def _validate_template(raw: dict[str, Any], vendor: str, source: str) -> CatalogCommandTemplate:
    required = ("name", "platform", "operation_type", "command_body")
    missing = [field for field in required if not raw.get(field)]
    if missing:
        raise ConfigValidationError(f"Command catalog entry {source} misses fields: {', '.join(missing)}")

    params = raw.get("params") or ()
    if not isinstance(params, (list, tuple)):
        raise ConfigValidationError(f"Command catalog entry {source} params must be a list")

    return CatalogCommandTemplate(
        name=str(raw["name"]),
        vendor=str(raw.get("vendor") or vendor),
        platform=str(raw["platform"]),
        operation_type=str(raw["operation_type"]),
        command_body=str(raw["command_body"]),
        is_active=bool(raw.get("is_active", True)),
        revision=int(raw.get("revision", 1)),
        description=str(raw.get("description", "")),
        params=tuple(str(param) for param in params),
        source=source,
        bound_entity_type=str(raw.get("bound_entity_type") or ""),
        bound_parameter=str(raw.get("bound_parameter") or ""),
        bound_direction=str(raw.get("bound_direction") or "both"),
        binding_priority=int(raw.get("binding_priority", 100)),
    )


class CommandCatalog:
    @staticmethod
    def file_templates() -> list[CatalogCommandTemplate]:
        templates: list[CatalogCommandTemplate] = []
        for file_name in CATALOG_FILES:
            content = resources.files(CATALOG_PACKAGE).joinpath(file_name).read_text(encoding="utf-8")
            data = yaml.safe_load(content) or {}
            vendor = str(data.get("vendor") or file_name.rsplit(".", 1)[0]).lower()
            raw_templates = data.get("templates") or []
            if not isinstance(raw_templates, list):
                raise ConfigValidationError(f"Command catalog {file_name} templates must be a list")
            for index, raw_template in enumerate(raw_templates, start=1):
                if not isinstance(raw_template, dict):
                    raise ConfigValidationError(f"Command catalog {file_name} entry #{index} must be a mapping")
                templates.append(_validate_template(raw_template, vendor, f"{file_name}#{index}"))
        return [template for template in templates if template.is_active]

    @classmethod
    def merge_with_database(
        cls,
        database_templates: list[CommandTemplate],
    ) -> list[CommandTemplate | CatalogCommandTemplate]:
        merged: dict[tuple[str, str, str, str], CommandTemplate | CatalogCommandTemplate] = {}
        for template in cls.file_templates():
            merged[template.key] = template
        for template in database_templates:
            if template.is_active:
                merged[template_key(template)] = template
        return list(merged.values())
