from .layers.configuration import (
    ConfigValidationError as ValidationError,
    CommandGenerator,
    ConfigurationRepository,
    ConfigurationValidator,
    NetworkPlanParser,
)
from .layers.network import ConnectionSession, ConnectionSessionError, DeviceConnectionManager, connect_device_cli
from .layers.tasks import TaskExecutor, UMLConfigurationService
from .layers.vcs import BackupWriteResult, ConfigurationVCS


class ConfigurationBackupService:
    @staticmethod
    def save_backup(device, config_text, task=None):
        return ConfigurationVCS.write_backup(device=device, config_text=config_text, task=task, source="runtime")

    @staticmethod
    def compare_versions(first: str, second: str):
        return ConfigurationRepository.compare_versions(first, second)
