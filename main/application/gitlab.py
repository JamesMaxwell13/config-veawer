from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from dcim.models import Device
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..application.configuration_yaml import ConfigurationYamlService
from ..application.interface_sync import InterfaceSyncService
from ..application.tasks import TaskExecutor
from ..domain.configuration import ConfigValidationError, NetworkPlanParser
from ..infrastructure.gitlab import (
    GitLabAPIError,
    GitLabClient,
    GitLabNotFoundError,
    GitLabPathBuilder,
)
from ..infrastructure.network import connect_device_cli
from ..infrastructure.vcs import ConfigurationVCS
from ..logging import device_log_context, logger
from ..models import (
    ConfigurationBackup,
    GitLabConfigMapping,
    GitLabIntegration,
    GitLabSyncLog,
    ScheduledTask,
)


class GitLabSyncConflict(Exception):
    pass


@dataclass(frozen=True)
class GitLabSyncResult:
    status: str
    message: str
    file_path: str = ""
    commit_sha: str = ""
    backup: ConfigurationBackup | None = None
    mapping: GitLabConfigMapping | None = None


class GitLabIntegrationService:
    SOURCE_GITLAB = "gitlab"
    SOURCE_PLUGIN = "plugin"
    DEFAULT_AUTO_APPLY_MAX_ATTEMPTS = 5
    DEFAULT_AUTO_APPLY_RETRY_DELAY_SECONDS = 1.0
    ACTUAL_SOURCES = {"runtime", "manual_refresh", "restore", "pre_apply"}

    @staticmethod
    def client_for(integration: GitLabIntegration) -> GitLabClient:
        return GitLabClient(integration.gitlab_url, integration.access_token_plain)

    @classmethod
    def log(
        cls,
        integration: GitLabIntegration,
        direction: str,
        status: str,
        message: str = "",
        mapping: GitLabConfigMapping | None = None,
        device: Device | None = None,
        backup: ConfigurationBackup | None = None,
        task: ScheduledTask | None = None,
        file_path: str = "",
        commit_sha: str = "",
    ) -> GitLabSyncLog:
        return GitLabSyncLog.objects.create(
            integration=integration,
            mapping=mapping,
            device=device or getattr(mapping, "device", None),
            configuration_backup=backup,
            task=task,
            direction=direction,
            file_path=file_path or getattr(mapping, "file_path", ""),
            commit_sha=commit_sha,
            status=status,
            message=message,
        )

    @classmethod
    def build_file_path(cls, integration: GitLabIntegration, device: Device) -> str:
        return GitLabPathBuilder.build(
            device,
            root_path=integration.root_path,
            pattern=integration.file_path_pattern,
        )

    @classmethod
    def get_or_create_mapping(
        cls,
        integration: GitLabIntegration,
        device: Device,
        backup: ConfigurationBackup | None = None,
    ) -> GitLabConfigMapping:
        mapping = GitLabConfigMapping.objects.filter(integration=integration, device=device).first()
        file_path = cls.build_file_path(integration, device)
        if mapping is None:
            mapping = GitLabConfigMapping.objects.create(
                integration=integration,
                device=device,
                configuration_backup=backup,
                file_path=file_path,
            )
            return mapping
        update_fields = []
        if not mapping.file_path:
            mapping.file_path = file_path
            update_fields.append("file_path")
        if backup and mapping.configuration_backup_id != backup.pk:
            mapping.configuration_backup = backup
            update_fields.append("configuration_backup")
        if update_fields:
            update_fields.append("last_updated")
            mapping.save(update_fields=update_fields)
        return mapping

    @classmethod
    def _validate_yaml(cls, yaml_text: str) -> None:
        if ConfigurationYamlService.is_yaml_config(yaml_text):
            ConfigurationYamlService.load_payload(yaml_text)
            return
        NetworkPlanParser.normalize_interfaces(NetworkPlanParser.parse_plan(yaml_text))

    @classmethod
    def _commit_sha_from_response(cls, response: dict[str, Any], metadata_commit: str = "") -> str:
        return (
            response.get("commit_id")
            or response.get("last_commit_id")
            or metadata_commit
            or ""
        )

    @classmethod
    def _plugin_config(cls) -> dict[str, Any]:
        return getattr(settings, "PLUGINS_CONFIG", {}).get("main", {})

    @classmethod
    def _auto_apply_max_attempts(cls) -> int:
        raw = cls._plugin_config().get("gitlab_auto_apply_max_attempts", cls.DEFAULT_AUTO_APPLY_MAX_ATTEMPTS)
        try:
            return min(20, max(1, int(raw)))
        except (TypeError, ValueError):
            return cls.DEFAULT_AUTO_APPLY_MAX_ATTEMPTS

    @classmethod
    def _auto_apply_retry_delay_seconds(cls) -> float:
        raw = cls._plugin_config().get(
            "gitlab_auto_apply_retry_delay_seconds",
            cls.DEFAULT_AUTO_APPLY_RETRY_DELAY_SECONDS,
        )
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return cls.DEFAULT_AUTO_APPLY_RETRY_DELAY_SECONDS

    @staticmethod
    def _read_device_running_config(device: Device) -> str:
        session, _profile, _check = connect_device_cli(device, verify_saved_config=False)
        try:
            return session.get_running_config()
        finally:
            session.disconnect()

    @classmethod
    def _latest_actual_backup(cls, device: Device) -> ConfigurationBackup | None:
        return (
            ConfigurationBackup.objects.filter(device=device, source__in=cls.ACTUAL_SOURCES)
            .order_by("-version")
            .first()
        )

    @classmethod
    def _snapshot_runtime_if_changed(
        cls,
        device: Device,
        running_config: str,
        baseline: ConfigurationBackup | None = None,
    ) -> tuple[ConfigurationBackup, bool]:
        baseline_backup = baseline or cls._latest_actual_backup(device)
        if baseline_backup and ConfigurationYamlService.backup_matches_running_config(
            device,
            baseline_backup.config_text,
            running_config,
            source="runtime",
        ):
            return baseline_backup, False
        runtime_backup = ConfigurationVCS.write_backup(device=device, config_text=running_config, source="runtime")
        return runtime_backup, True

    @staticmethod
    def _set_mapping_apply_state(
        mapping: GitLabConfigMapping,
        *,
        state: str,
        attempts: int | None = None,
        actual_backup: ConfigurationBackup | None = None,
        last_attempt_at=None,
        last_verified_at=None,
        error: str | None = None,
    ) -> None:
        update_fields: list[str] = []
        if mapping.apply_state != state:
            mapping.apply_state = state
            update_fields.append("apply_state")
        if attempts is not None and mapping.apply_attempts != attempts:
            mapping.apply_attempts = attempts
            update_fields.append("apply_attempts")
        if actual_backup is not None and mapping.actual_backup_id != actual_backup.pk:
            mapping.actual_backup = actual_backup
            update_fields.append("actual_backup")
        if last_attempt_at is not None:
            mapping.last_apply_attempt_at = last_attempt_at
            update_fields.append("last_apply_attempt_at")
        if last_verified_at is not None:
            mapping.last_apply_verified_at = last_verified_at
            update_fields.append("last_apply_verified_at")
        if error is not None and mapping.last_apply_error != error:
            mapping.last_apply_error = error
            update_fields.append("last_apply_error")
        if update_fields:
            mapping.save(update_fields=tuple(update_fields + ["last_updated"]))

    @classmethod
    def _auto_apply_gitlab_backup(
        cls,
        integration: GitLabIntegration,
        mapping: GitLabConfigMapping,
        backup: ConfigurationBackup,
        file_path: str,
        commit_sha: str,
    ) -> GitLabSyncResult:
        max_attempts = cls._auto_apply_max_attempts()
        retry_delay = cls._auto_apply_retry_delay_seconds()
        for attempt in range(1, max_attempts + 1):
            attempt_at = timezone.now()
            cls._set_mapping_apply_state(
                mapping,
                state=GitLabConfigMapping.APPLY_STATE_APPLYING,
                attempts=attempt,
                last_attempt_at=attempt_at,
                error="",
            )
            try:
                running_after_apply, _apply_message = TaskExecutor.apply_backup_to_device_with_running(backup)
            except Exception as exc:
                message = f"GitLab auto-apply attempt {attempt}/{max_attempts} failed: {exc}"
                cls._set_mapping_apply_state(
                    mapping,
                    state=GitLabConfigMapping.APPLY_STATE_FAILED,
                    attempts=attempt,
                    last_attempt_at=attempt_at,
                    error=str(exc),
                )
                cls.log(
                    integration,
                    GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                    GitLabSyncLog.STATUS_FAILED,
                    message,
                    mapping=mapping,
                    device=backup.device,
                    backup=backup,
                    file_path=file_path,
                    commit_sha=commit_sha,
                )
                if attempt >= max_attempts:
                    return GitLabSyncResult("failed", message, file_path, commit_sha, backup, mapping)
                if retry_delay > 0:
                    time.sleep(retry_delay)
                continue

            if ConfigurationYamlService.backup_matches_running_config(
                backup.device,
                backup.config_text,
                running_after_apply,
                source="gitlab_apply",
            ):
                verified_at = timezone.now()
                cls._set_mapping_apply_state(
                    mapping,
                    state=GitLabConfigMapping.APPLY_STATE_VERIFIED,
                    attempts=attempt,
                    actual_backup=backup,
                    last_attempt_at=attempt_at,
                    last_verified_at=verified_at,
                    error="",
                )
                message = f"Configuration imported from GitLab and verified on device (attempt {attempt}/{max_attempts})."
                cls.log(
                    integration,
                    GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                    GitLabSyncLog.STATUS_SUCCESS,
                    message,
                    mapping=mapping,
                    device=backup.device,
                    backup=backup,
                    file_path=file_path,
                    commit_sha=commit_sha,
                )
                return GitLabSyncResult("success", message, file_path, commit_sha, backup, mapping)

            actual_backup, _created = cls._snapshot_runtime_if_changed(
                backup.device,
                running_after_apply,
                baseline=mapping.actual_backup,
            )
            mismatch_message = (
                f"GitLab auto-apply verification mismatch on attempt {attempt}/{max_attempts}: "
                "device runtime does not match imported GitLab configuration."
            )
            cls._set_mapping_apply_state(
                mapping,
                state=GitLabConfigMapping.APPLY_STATE_DRIFT,
                attempts=attempt,
                actual_backup=actual_backup,
                last_attempt_at=attempt_at,
                error=mismatch_message,
            )
            if attempt >= max_attempts:
                cls.log(
                    integration,
                    GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                    GitLabSyncLog.STATUS_FAILED,
                    mismatch_message,
                    mapping=mapping,
                    device=backup.device,
                    backup=backup,
                    file_path=file_path,
                    commit_sha=commit_sha,
                )
                return GitLabSyncResult("failed", mismatch_message, file_path, commit_sha, backup, mapping)

            cls.log(
                integration,
                GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                GitLabSyncLog.STATUS_CONFLICT,
                mismatch_message,
                mapping=mapping,
                device=backup.device,
                backup=backup,
                file_path=file_path,
                commit_sha=commit_sha,
            )
            if retry_delay > 0:
                time.sleep(retry_delay)

        message = "GitLab auto-apply exhausted retries."
        return GitLabSyncResult("failed", message, file_path, commit_sha, backup, mapping)

    @classmethod
    def push_backup_to_gitlab(
        cls,
        backup: ConfigurationBackup,
        integration: GitLabIntegration | None = None,
        source: str = SOURCE_PLUGIN,
        raise_on_conflict: bool = False,
    ) -> list[GitLabSyncResult]:
        if source == cls.SOURCE_GITLAB or str(backup.source).startswith(cls.SOURCE_GITLAB):
            return []

        integrations = [integration] if integration else list(GitLabIntegration.objects.filter(enabled=True))
        results: list[GitLabSyncResult] = []
        for item in integrations:
            mapping = cls.get_or_create_mapping(item, backup.device, backup)
            if not mapping.sync_enabled:
                cls.log(
                    item,
                    GitLabSyncLog.DIRECTION_PLUGIN_TO_GITLAB,
                    GitLabSyncLog.STATUS_SKIPPED,
                    "Mapping sync is disabled.",
                    mapping=mapping,
                    backup=backup,
                )
                continue

            client = cls.client_for(item)
            try:
                try:
                    metadata = client.get_file_metadata(item.project_id, mapping.file_path, item.branch)
                    exists = True
                except GitLabNotFoundError:
                    metadata = None
                    exists = False

                commit_message = f"Update config for {backup.device.name} from NetBox Config Weaver"
                if exists:
                    response = client.update_file(
                        item.project_id,
                        mapping.file_path,
                        item.branch,
                        backup.config_text,
                        commit_message,
                        last_commit_id=metadata.last_commit_id if metadata else None,
                    )
                else:
                    response = client.create_file(
                        item.project_id,
                        mapping.file_path,
                        item.branch,
                        backup.config_text,
                        commit_message,
                    )
                try:
                    refreshed = client.get_file_metadata(item.project_id, mapping.file_path, item.branch)
                    commit_sha = refreshed.last_commit_id
                except GitLabAPIError:
                    commit_sha = cls._commit_sha_from_response(response, metadata.last_commit_id if metadata else "")

                mapping.configuration_backup = backup
                mapping.last_gitlab_commit_sha = commit_sha
                mapping.last_plugin_update_at = timezone.now()
                mapping.save(
                    update_fields=(
                        "configuration_backup",
                        "last_gitlab_commit_sha",
                        "last_plugin_update_at",
                        "last_updated",
                    )
                )
                message = "Configuration force-pushed to GitLab." if exists else "Configuration pushed to GitLab."
                cls.log(
                    item,
                    GitLabSyncLog.DIRECTION_PLUGIN_TO_GITLAB,
                    GitLabSyncLog.STATUS_SUCCESS,
                    message,
                    mapping=mapping,
                    backup=backup,
                    commit_sha=commit_sha,
                )
                results.append(GitLabSyncResult("success", message, mapping.file_path, commit_sha, backup, mapping))
            except GitLabSyncConflict:
                raise
            except Exception as exc:
                logger.exception("GitLab push failed backup_id=%s integration_id=%s", backup.pk, item.pk)
                cls.log(
                    item,
                    GitLabSyncLog.DIRECTION_PLUGIN_TO_GITLAB,
                    GitLabSyncLog.STATUS_FAILED,
                    str(exc),
                    mapping=mapping,
                    backup=backup,
                )
                results.append(GitLabSyncResult("failed", str(exc), mapping.file_path, backup=backup, mapping=mapping))
        return results

    @classmethod
    def find_device_for_file(cls, integration: GitLabIntegration, file_path: str) -> Device | None:
        mapping = GitLabConfigMapping.objects.filter(
            integration=integration,
            file_path=file_path,
            sync_enabled=True,
        ).select_related("device").first()
        if mapping:
            return mapping.device

        devices = Device.objects.select_related(
            "site",
            "location",
            "rack",
            "role",
            "platform",
            "device_type__manufacturer",
        )
        for device in devices:
            if cls.build_file_path(integration, device) == file_path:
                return device
        return None

    @classmethod
    def sync_file_from_gitlab(
        cls,
        integration: GitLabIntegration,
        file_path: str,
        ref: str,
        commit_sha: str = "",
    ) -> GitLabSyncResult:
        device = cls.find_device_for_file(integration, file_path)
        if device is None:
            message = f"No NetBox device matches {file_path}."
            cls.log(
                integration,
                GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                GitLabSyncLog.STATUS_SKIPPED,
                message,
                file_path=file_path,
                commit_sha=commit_sha,
            )
            return GitLabSyncResult("skipped", message, file_path, commit_sha)

        mapping = cls.get_or_create_mapping(integration, device)
        client = cls.client_for(integration)
        try:
            yaml_text = client.get_raw_file(integration.project_id, file_path, ref)
            cls._validate_yaml(yaml_text)
            if not commit_sha:
                try:
                    commit_sha = client.get_file_metadata(integration.project_id, file_path, ref).last_commit_id
                except GitLabAPIError:
                    pass
        except Exception as exc:
            cls.log(
                integration,
                GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                GitLabSyncLog.STATUS_FAILED,
                str(exc),
                mapping=mapping,
                device=device,
                file_path=file_path,
                commit_sha=commit_sha,
            )
            return GitLabSyncResult("failed", str(exc), file_path, commit_sha, mapping=mapping)

        runtime_snapshot: ConfigurationBackup | None = mapping.actual_backup
        if integration.auto_apply:
            try:
                running_config = cls._read_device_running_config(device)
                runtime_snapshot, _created = cls._snapshot_runtime_if_changed(
                    device,
                    running_config,
                    baseline=runtime_snapshot,
                )
            except Exception as exc:
                message = f"GitLab auto-apply preflight failed: {exc}"
                cls.log(
                    integration,
                    GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                    GitLabSyncLog.STATUS_FAILED,
                    message,
                    mapping=mapping,
                    device=device,
                    file_path=file_path,
                    commit_sha=commit_sha,
                )
                cls._set_mapping_apply_state(
                    mapping,
                    state=GitLabConfigMapping.APPLY_STATE_FAILED,
                    error=message,
                )
                return GitLabSyncResult("failed", message, file_path, commit_sha, mapping=mapping)

        with transaction.atomic():
            backup = ConfigurationBackup.objects.create(
                device=device,
                version=cls._next_backup_version(device),
                version_name=f"gitlab-{timezone.now():%Y-%m-%d-%H-%M}",
                config_text=yaml_text,
                source=cls.SOURCE_GITLAB,
                commit_hash=commit_sha,
                config_checksum=ConfigurationYamlService.checksum(yaml_text),
                redacted=True,
            )
            mapping.configuration_backup = backup
            mapping.file_path = file_path
            mapping.last_gitlab_commit_sha = commit_sha or mapping.last_gitlab_commit_sha
            mapping.last_gitlab_update_at = timezone.now()
            mapping.apply_state = GitLabConfigMapping.APPLY_STATE_PENDING
            mapping.apply_attempts = 0
            mapping.last_apply_error = ""
            if runtime_snapshot is not None:
                mapping.actual_backup = runtime_snapshot
            mapping.save(
                update_fields=(
                    "configuration_backup",
                    "file_path",
                    "last_gitlab_commit_sha",
                    "last_gitlab_update_at",
                    "apply_state",
                    "apply_attempts",
                    "last_apply_error",
                    "actual_backup",
                    "last_updated",
                )
            )

            if mapping.scheduled_task_id:
                mapping.scheduled_task = None
                mapping.save(update_fields=("scheduled_task", "last_updated"))

        InterfaceSyncService.sync_from_configuration_backup(backup, origin="gitlab_import")

        if integration.auto_apply:
            return cls._auto_apply_gitlab_backup(
                integration=integration,
                mapping=mapping,
                backup=backup,
                file_path=file_path,
                commit_sha=commit_sha,
            )

        message = "Configuration imported from GitLab."
        cls.log(
            integration,
            GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
            GitLabSyncLog.STATUS_SUCCESS,
            message,
            mapping=mapping,
            device=device,
            backup=backup,
            file_path=file_path,
            commit_sha=commit_sha,
        )
        logger.info("GitLab configuration synced %s file_path=%s", device_log_context(device), file_path)
        return GitLabSyncResult("success", message, file_path, commit_sha, backup, mapping)

    @staticmethod
    def _next_backup_version(device: Device) -> int:
        last = ConfigurationBackup.objects.filter(device=device).order_by("-version").first()
        return 1 if not last else last.version + 1

    @classmethod
    def handle_push_event(cls, integration: GitLabIntegration, payload: dict[str, Any]) -> list[GitLabSyncResult]:
        ref = payload.get("ref", "")
        expected_ref = f"refs/heads/{integration.branch}"
        if ref != expected_ref:
            message = f"Ignored branch {ref}; expected {expected_ref}."
            cls.log(
                integration,
                GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                GitLabSyncLog.STATUS_SKIPPED,
                message,
            )
            return [GitLabSyncResult("skipped", message)]

        commit_sha = payload.get("checkout_sha") or payload.get("after") or ""
        changed_paths: set[str] = set()
        removed_paths: set[str] = set()
        for commit in payload.get("commits") or []:
            for key in ("added", "modified"):
                changed_paths.update(commit.get(key) or [])
            removed_paths.update(commit.get("removed") or [])

        results: list[GitLabSyncResult] = []
        root = GitLabPathBuilder.normalize_path(integration.root_path)
        for file_path in sorted(changed_paths):
            normalized = GitLabPathBuilder.normalize_path(file_path)
            if normalized in removed_paths:
                continue
            if not (normalized.endswith(".yaml") or normalized.endswith(".yml")):
                continue
            if not normalized.startswith(f"{root}/") and normalized != root:
                continue
            results.append(cls.sync_file_from_gitlab(integration, normalized, commit_sha or integration.branch, commit_sha=commit_sha))

        integration.last_sync_at = timezone.now()
        integration.save(update_fields=("last_sync_at", "last_updated"))
        if not results:
            message = "No YAML configuration files changed."
            cls.log(
                integration,
                GitLabSyncLog.DIRECTION_GITLAB_TO_PLUGIN,
                GitLabSyncLog.STATUS_SKIPPED,
                message,
                commit_sha=commit_sha,
            )
            return [GitLabSyncResult("skipped", message, commit_sha=commit_sha)]
        return results

    @classmethod
    def sync_from_gitlab(cls, integration: GitLabIntegration) -> list[GitLabSyncResult]:
        mappings = GitLabConfigMapping.objects.filter(integration=integration, sync_enabled=True)
        results = [
            cls.sync_file_from_gitlab(integration, mapping.file_path, integration.branch)
            for mapping in mappings
        ]
        integration.last_sync_at = timezone.now()
        integration.save(update_fields=("last_sync_at", "last_updated"))
        return results

    @classmethod
    def push_to_gitlab(cls, integration: GitLabIntegration) -> list[GitLabSyncResult]:
        backups = []
        for device in Device.objects.all():
            backup = ConfigurationBackup.objects.filter(device=device).order_by("-version").first()
            if backup:
                backups.append(backup)
        results: list[GitLabSyncResult] = []
        for backup in backups:
            results.extend(cls.push_backup_to_gitlab(backup, integration=integration))
        return results

    @classmethod
    def rebuild_paths(cls, integration: GitLabIntegration) -> int:
        count = 0
        for mapping in GitLabConfigMapping.objects.filter(integration=integration).select_related("device"):
            mapping.file_path = cls.build_file_path(integration, mapping.device)
            mapping.save(update_fields=("file_path", "last_updated"))
            count += 1
        return count
