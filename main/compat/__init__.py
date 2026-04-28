"""Compatibility exports for older plugin internals."""

from .configuration import CommandGenerator, ConfigurationRepository, ConfigurationValidator, NetworkPlanParser
from .network import ConnectionSession, DeviceConnectionManager, connect_device_cli
from .tasks import TaskExecutor, UMLConfigurationService
from .vcs import ConfigurationVCS

__all__ = [
    "CommandGenerator",
    "ConfigurationRepository",
    "ConfigurationValidator",
    "NetworkPlanParser",
    "ConnectionSession",
    "DeviceConnectionManager",
    "connect_device_cli",
    "TaskExecutor",
    "UMLConfigurationService",
    "ConfigurationVCS",
]
