from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import hashlib
import re
import subprocess

from dcim.models import Device
from django.conf import settings
from django.utils import timezone

from ..application.configuration_yaml import ConfigurationYamlService
from ..logging import device_log_context, logger
from ..models import ConfigurationBackup, NetworkTask


@dataclass
class BackupWriteResult:
    version: int
    commit_hash: str
    file_name: str


class ConfigurationVCS:
    @staticmethod
    def repo_path() -> Path:
        plugin_cfg = getattr(settings, "PLUGINS_CONFIG", {}).get("main", {})
        configured = plugin_cfg.get("vcs_repo_path")
        path = Path(configured) if configured else Path(getattr(settings, "MEDIA_ROOT", "/tmp")) / "config_weaver_repo"

        path.mkdir(parents=True, exist_ok=True)
        if not (path / ".git").exists():
            logger.info("Initializing configuration VCS repository path=%s", path)
            try:
                subprocess.run(["git", "init"], cwd=path, check=True)
                subprocess.run(["git", "config", "user.name", "Config Weaver"], cwd=path, check=True)
                subprocess.run(["git", "config", "user.email", "config-weaver@localhost"], cwd=path, check=True)
            except Exception:
                logger.exception("Failed to initialize configuration VCS repository path=%s", path)
                raise
        return path

    @staticmethod
    def safe_file_name(raw: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw).strip("_")
        return cleaned or "device"

    @staticmethod
    def next_version(device: Device) -> int:
        last = ConfigurationBackup.objects.filter(device=device).order_by("-version").first()
        return 1 if not last else last.version + 1

    @classmethod
    def build_version_name(cls, device: Device, dt: datetime | None = None) -> str:
        dt = dt or timezone.now()
        safe_name = cls.safe_file_name(device.name)
        return f"{dt:%Y-%m-%d-%H-%M}-{safe_name}"

    @classmethod
    def build_unique_version_name(
        cls,
        device: Device,
        dt: datetime | None = None,
        exclude_pk: int | None = None,
    ) -> str:
        max_length = ConfigurationBackup._meta.get_field("version_name").max_length
        base_name = cls.build_version_name(device, dt)
        existing_qs = ConfigurationBackup.objects.filter(device=device)
        if exclude_pk:
            existing_qs = existing_qs.exclude(pk=exclude_pk)
        existing_names = set(existing_qs.values_list("version_name", flat=True))

        candidate = base_name[:max_length]
        if candidate not in existing_names:
            return candidate

        suffix_number = 1
        while True:
            suffix = f"_{suffix_number}"
            candidate = f"{base_name[:max_length - len(suffix)]}{suffix}"
            if candidate not in existing_names:
                return candidate
            suffix_number += 1

    @classmethod
    def write_backup(
        cls,
        device: Device,
        config_text: str,
        task: NetworkTask | None = None,
        source: str = "runtime",
    ) -> ConfigurationBackup:
        repo = cls.repo_path()
        version = cls.next_version(device)
        safe_name = cls.safe_file_name(device.name)
        file_name = f"{safe_name}__v{version}.yaml"

        version_name = cls.build_unique_version_name(device)
        yaml_text = (
            config_text
            if ConfigurationYamlService.is_yaml_config(config_text)
            else ConfigurationYamlService.running_config_to_yaml(device, config_text, source=source)
        )

        checksum = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
        logger.info(
            "Writing configuration backup %s source=%s task=%s version=%s version_name=%s checksum=%s",
            device_log_context(device),
            source,
            task.name if task else None,
            version,
            version_name,
            checksum,
        )
        try:
            (repo / file_name).write_text(yaml_text, encoding="utf-8")
            subprocess.run(["git", "add", file_name], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", f"backup({safe_name}): version {version}"], cwd=repo, check=True)
            commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip()
        except Exception:
            logger.exception(
                "Failed to write configuration backup %s source=%s version=%s file=%s",
                device_log_context(device),
                source,
                version,
                file_name,
            )
            raise

        backup = ConfigurationBackup.objects.create(
            device=device,
            task=task,
            version=version,
            version_name=version_name,
            config_text=yaml_text,
            source=source,
            commit_hash=commit_hash,
            config_checksum=checksum,
            redacted=True,
        )
        logger.info(
            "Configuration backup created %s source=%s version=%s backup_id=%s commit=%s checksum=%s",
            device_log_context(device),
            source,
            backup.version,
            backup.pk,
            commit_hash,
            checksum,
        )
        return backup
