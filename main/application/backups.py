from __future__ import annotations

from ..infrastructure.repositories import ConfigurationRepository
from ..infrastructure.vcs import ConfigurationVCS


class ConfigurationBackupService:
    @staticmethod
    def save_backup(device, config_text, task=None):
        return ConfigurationVCS.write_backup(device=device, config_text=config_text, task=task, source="runtime")

    @staticmethod
    def compare_versions(first: str, second: str):
        return ConfigurationRepository.compare_versions(first, second)
