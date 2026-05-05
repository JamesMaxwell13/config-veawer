from __future__ import annotations

from difflib import unified_diff

from django.core.cache import cache

from ..domain.command_catalog import CatalogCommandTemplate, CommandCatalog
from ..models import CommandTemplate, ConfigurationBackup


class ConfigurationRepository:
    @staticmethod
    def latest_backup_for_device(device_id: int) -> ConfigurationBackup | None:
        return ConfigurationBackup.objects.filter(device_id=device_id).order_by("-version").first()

    @staticmethod
    def compare_versions(first: str, second: str) -> list[str]:
        return list(unified_diff(first.splitlines(), second.splitlines(), lineterm=""))

    @staticmethod
    def active_templates() -> list[CommandTemplate | CatalogCommandTemplate]:
        key = "cw:templates:active"
        cached = cache.get(key)
        if cached is not None:
            return cached
        templates = CommandCatalog.merge_with_database(list(CommandTemplate.objects.filter(is_active=True)))
        cache.set(key, templates, timeout=120)
        return templates
