from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections
from django.utils import timezone

from ..domain.configuration import (
    CommandGenerator,
    ConfigValidationError,
    ConfigurationValidator,
    NetworkPlanParser,
)
from .configuration_yaml import ConfigurationYamlService
from ..infrastructure.network import ConnectionSession, DeviceConnectionManager, connect_device_cli
from ..infrastructure.repositories import ConfigurationRepository
from ..infrastructure.vcs import ConfigurationVCS
from ..logging import device_log_context, logger, task_log_context
from ..models import DevicePlatformProfile, ScheduledTask


class TaskExecutor:
    DEFAULT_SCHEDULER_MAX_WORKERS = 8

    @staticmethod
    def preview_commands(task: ScheduledTask) -> list[str]:
        if not task.task:
            raise ConfigValidationError("YAML task is required for apply_scenario task")

        profile = DeviceConnectionManager.get_profile(task.target_device)
        if not profile:
            raise ConfigValidationError(f"No active device profile for {task.target_device.name}")

        task_stamp = int(task.last_updated.timestamp()) if task.last_updated else 0
        task_hash = hashlib.sha256(task.task.encode("utf-8")).hexdigest()[:12]
        cache_key = f"cw:preview:{task.pk}:{task_stamp}:{task_hash}:{profile.pk}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        plan = NetworkPlanParser.normalize_interfaces(NetworkPlanParser.parse_plan(task.task))
        commands = CommandGenerator.generate_commands(plan, ConfigurationRepository.active_templates(), profile)
        commands = ConnectionSession.with_save_command(commands, profile.platform)

        valid, errors = ConfigurationValidator.validate_commands(commands)
        if not valid:
            raise ConfigValidationError("; ".join(errors))

        cache.set(cache_key, commands, timeout=120)
        return commands

    @staticmethod
    def _apply_commands(profile: DevicePlatformProfile, task: ScheduledTask, commands: list[str]) -> str:
        logger.info(
            "Applying command scenario %s command_count=%s %s",
            task_log_context(task),
            len(commands),
            device_log_context(task.target_device, profile),
        )
        session, _profile, _check = connect_device_cli(task.target_device, verify_saved_config=True)
        try:
            before_config = session.get_running_config()
            before_backup = ConfigurationVCS.write_backup(
                task.target_device,
                before_config,
                task=task,
                source="pre_apply",
            )
            logger.info(
                "Pre-apply configuration backup created %s task_id=%s backup_id=%s version=%s",
                device_log_context(task.target_device, profile),
                task.pk,
                before_backup.pk,
                before_backup.version,
            )
            session.send_config_set(commands)
            running = session.get_running_config()
        finally:
            session.disconnect()

        configuration = ConfigurationVCS.write_backup(task.target_device, running, task=None, source="runtime")
        logger.info(
            "Command scenario applied %s command_count=%s configuration_version=%s backup_id=%s",
            task_log_context(task),
            len(commands),
            configuration.version,
            configuration.pk,
        )
        return (
            f"Сценарий применен через {profile.platform}; "
            f"создана конфигурация v{configuration.version}"
        )

    @classmethod
    def _run_apply_scenario(cls, task: ScheduledTask) -> str:
        profile = DeviceConnectionManager.get_profile(task.target_device)
        if not profile:
            raise ConfigValidationError(f"No active device profile for {task.target_device.name}")
        commands = cls.preview_commands(task)
        return cls._apply_commands(profile, task, commands)

    @staticmethod
    def _run_backup(task: ScheduledTask) -> str:
        logger.info("Running configuration backup task %s", task_log_context(task))
        session, _profile, _check = connect_device_cli(task.target_device, verify_saved_config=True)
        try:
            current_config = session.get_running_config()
        finally:
            session.disconnect()

        configuration = ConfigurationVCS.write_backup(task.target_device, current_config, source="runtime")
        logger.info(
            "Configuration backup task completed %s configuration_version=%s backup_id=%s",
            task_log_context(task),
            configuration.version,
            configuration.pk,
        )
        return f"Конфигурация сохранена: v{configuration.version}"

    @staticmethod
    def _run_healthcheck(task: ScheduledTask) -> str:
        logger.info("Running healthcheck task %s", task_log_context(task))
        try:
            session, _profile, _check = connect_device_cli(task.target_device, verify_saved_config=False)
            try:
                alive = session.is_alive()
            finally:
                session.disconnect()
            logger.info("Healthcheck task completed %s alive=%s", task_log_context(task), alive)
            return f"Healthcheck {'OK' if alive else 'FAILED'} for {task.target_device.name}"
        except Exception as exc:
            logger.warning("Healthcheck task failed %s error=%s", task_log_context(task), exc)
            return f"Healthcheck FAILED for {task.target_device.name}: {exc}"

    @staticmethod
    def restore_backup_to_device(backup) -> str:
        logger.info(
            "Restoring configuration backup %s backup_id=%s source_version=%s",
            device_log_context(backup.device),
            backup.pk,
            backup.version,
        )
        session, profile, _check = connect_device_cli(backup.device, verify_saved_config=False)
        try:
            commands = ConfigurationYamlService.yaml_to_commands(backup.config_text, profile)
            commands = ConnectionSession.with_save_command(commands, getattr(profile, "platform", None))
            valid, errors = ConfigurationValidator.validate_commands(commands)
            if not valid:
                logger.warning(
                    "Restore configuration validation failed %s backup_id=%s error_count=%s",
                    device_log_context(backup.device, profile),
                    backup.pk,
                    len(errors),
                )
                raise ConfigValidationError("; ".join(errors))
            logger.info(
                "Sending restore configuration commands %s backup_id=%s command_count=%s",
                device_log_context(backup.device, profile),
                backup.pk,
                len(commands),
            )
            session.send_config_set(commands)
            running = session.get_running_config()
        finally:
            session.disconnect()

        if ConfigurationYamlService.backup_matches_running_config(backup.device, backup.config_text, running):
            logger.info(
                "Configuration backup restored without new version %s backup_id=%s source_version=%s",
                device_log_context(backup.device, profile),
                backup.pk,
                backup.version,
            )
            return (
                f"Конфигурация v{backup.version} отправлена на устройство; "
                "текущая конфигурация совпадает, новая версия не создана"
            )

        new_configuration = ConfigurationVCS.write_backup(
            backup.device,
            running,
            task=backup.task,
            source="restore",
        )
        logger.info(
            "Configuration backup restored %s backup_id=%s source_version=%s new_version=%s new_backup_id=%s",
            device_log_context(backup.device, profile),
            backup.pk,
            backup.version,
            new_configuration.version,
            new_configuration.pk,
        )
        return (
            f"Конфигурация v{backup.version} отправлена на устройство; "
            f"текущая конфигурация сохранена как v{new_configuration.version}"
        )

    @staticmethod
    def _reschedule_if_periodic(task: ScheduledTask) -> None:
        if not task.run_every_seconds:
            return
        task.schedule_time = timezone.now() + timedelta(seconds=task.run_every_seconds)
        task.save(update_fields=("schedule_time", "last_updated"))
        logger.info(
            "Periodic task rescheduled %s next_run=%s interval_seconds=%s",
            task_log_context(task),
            task.schedule_time.isoformat(),
            task.run_every_seconds,
        )

    @classmethod
    def run_task(cls, task: ScheduledTask) -> None:
        logger.info("Executing task %s", task_log_context(task))
        task.update_status(ScheduledTask.STATUS_RUNNING, "Task started")
        try:
            if task.task_type == ScheduledTask.TYPE_APPLY_SCENARIO:
                message = cls._run_apply_scenario(task)
            elif task.task_type == ScheduledTask.TYPE_BACKUP:
                message = cls._run_backup(task)
            elif task.task_type == ScheduledTask.TYPE_HEALTHCHECK:
                message = cls._run_healthcheck(task)
            else:
                raise ConfigValidationError(f"Unsupported task type: {task.task_type}")

            task.retry_count = 0
            task.save(update_fields=("retry_count", "last_updated"))
            task.update_status(ScheduledTask.STATUS_SUCCESS, message)
            logger.info("Scheduled task completed %s result=%s", task_log_context(task), message)
            cls._reschedule_if_periodic(task)
        except Exception as exc:
            logger.exception("Scheduled task failed %s error=%s", task_log_context(task), exc)
            task.retry_count += 1
            if task.retry_count <= task.max_retries:
                task.status = ScheduledTask.STATUS_PENDING
                task.result_message = f"Retry scheduled ({task.retry_count}/{task.max_retries}): {exc}"
                task.schedule_time = timezone.now() + timedelta(seconds=30)
                task.save(update_fields=("status", "result_message", "retry_count", "schedule_time", "last_updated"))
                logger.warning(
                    "Scheduled task retry queued %s retry=%s max_retries=%s next_run=%s",
                    task_log_context(task),
                    task.retry_count,
                    task.max_retries,
                    task.schedule_time.isoformat(),
                )
            else:
                task.save(update_fields=("retry_count", "last_updated"))
                task.update_status(ScheduledTask.STATUS_FAILED, str(exc))
                logger.warning("Scheduled task marked failed %s", task_log_context(task))

    @classmethod
    def scheduler_max_workers(cls) -> int:
        plugin_cfg = getattr(settings, "PLUGINS_CONFIG", {}).get("main", {})
        raw_value = plugin_cfg.get("scheduler_max_workers", cls.DEFAULT_SCHEDULER_MAX_WORKERS)
        try:
            return max(1, int(raw_value))
        except (TypeError, ValueError):
            return cls.DEFAULT_SCHEDULER_MAX_WORKERS

    @classmethod
    def _run_task_by_id(cls, task_id: int) -> None:
        close_old_connections()
        try:
            task = ScheduledTask.objects.get(pk=task_id)
            if task.status == ScheduledTask.STATUS_RUNNING or not task.is_due():
                return
            cls.run_task(task)
        finally:
            close_old_connections()

    @classmethod
    def run_due_tasks(cls) -> int:
        due = (
            ScheduledTask.objects.filter(schedule_time__lte=timezone.now())
            .exclude(status=ScheduledTask.STATUS_RUNNING)
        )
        due_task_ids = [task.pk for task in due if task.is_due()]
        if not due_task_ids:
            return 0

        with ThreadPoolExecutor(max_workers=cls.scheduler_max_workers()) as executor:
            futures = [executor.submit(cls._run_task_by_id, task_id) for task_id in due_task_ids]
            for future in futures:
                future.result()

        return len(due_task_ids)
