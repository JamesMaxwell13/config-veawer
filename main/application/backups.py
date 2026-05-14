from __future__ import annotations

from .configuration_yaml import ConfigurationYamlService
from ..domain.security import redact_secrets
from ..infrastructure.network import connect_device_cli
from ..infrastructure.repositories import ConfigurationRepository
from ..infrastructure.vcs import ConfigurationVCS
from ..logging import device_log_context, logger


class ConfigurationService:
    @staticmethod
    def save_backup(device, config_text, task=None):
        return ConfigurationVCS.write_backup(device=device, config_text=config_text, task=task, source="runtime")

    @staticmethod
    def compare_versions(first: str, second: str):
        return ConfigurationRepository.compare_versions(first, second)

    @staticmethod
    def refresh_device_config(device, compare_to=None, source: str = "manual_refresh") -> dict:
        logger.info(
            "Manual configuration refresh requested %s compare_backup_id=%s",
            device_log_context(device),
            getattr(compare_to, "pk", None),
        )
        session, profile, _check = connect_device_cli(device, verify_saved_config=False)
        try:
            running_config = session.get_running_config()
        finally:
            session.disconnect()

        yaml_config = ConfigurationYamlService.running_config_to_yaml(device, running_config, source=source)
        checksum = ConfigurationYamlService.checksum(yaml_config)
        legacy_checksum = ConfigurationYamlService.checksum(redact_secrets(running_config))
        baseline = compare_to or ConfigurationRepository.latest_backup_for_device(device.pk)
        if baseline and (
            baseline.config_checksum in {checksum, legacy_checksum}
            or ConfigurationYamlService.backup_matches_running_config(device, baseline.config_text, running_config, source=source)
        ):
            logger.info(
                "Manual configuration refresh completed unchanged %s baseline_backup_id=%s",
                device_log_context(device, profile),
                baseline.pk,
            )
            return {
                "changed": False,
                "backup": baseline,
                "baseline": baseline,
                "checksum": checksum,
                "reason": "unchanged",
            }

        backup = ConfigurationVCS.write_backup(device=device, config_text=yaml_config, source=source)
        logger.info(
            "Manual configuration refresh created backup %s baseline_backup_id=%s backup_id=%s version=%s",
            device_log_context(device, profile),
            getattr(baseline, "pk", None),
            backup.pk,
            backup.version,
        )
        return {
            "changed": True,
            "backup": backup,
            "baseline": baseline,
            "checksum": checksum,
            "reason": "changed" if baseline else "no_backup",
        }


ConfigurationBackupService = ConfigurationService
