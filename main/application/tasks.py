from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

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
from ..infrastructure.network import DeviceConnectionManager, connect_device_cli
from ..infrastructure.repositories import ConfigurationRepository
from ..infrastructure.vcs import ConfigurationVCS
from ..models import DevicePlatformProfile, ScheduledTask


class TaskExecutor:
    DEFAULT_SCHEDULER_MAX_WORKERS = 8

    @staticmethod
    def preview_commands(task: ScheduledTask) -> list[str]:
        if not task.task:
            raise ConfigValidationError("Task is required for apply_scenario task")

        profile = DeviceConnectionManager.get_profile(task.target_device)
        if not profile:
            raise ConfigValidationError(f"No active device profile for {task.target_device.name}")

        task_stamp = int(task.task.last_updated.timestamp()) if task.task.last_updated else 0
        cache_key = f"cw:preview:{task.pk}:{task_stamp}:{profile.pk}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        plan = NetworkPlanParser.normalize_interfaces(NetworkPlanParser.parse_plan(task.task.plan_yaml))
        commands = CommandGenerator.generate_commands(plan, ConfigurationRepository.active_templates(), profile)

        valid, errors = ConfigurationValidator.validate_commands(commands)
        if not valid:
            raise ConfigValidationError("; ".join(errors))

        cache.set(cache_key, commands, timeout=120)
        return commands

    @staticmethod
    def _apply_commands(profile: DevicePlatformProfile, task: ScheduledTask, commands: list[str]) -> str:
        session, _profile, _check = connect_device_cli(task.target_device, verify_saved_config=True)
        try:
            session.send_config_set(commands)
            running = session.get_running_config()
        finally:
            session.disconnect()

        configuration = ConfigurationVCS.write_backup(task.target_device, running, task=task.task, source="runtime")
        return f"Сценарий применен через {profile.platform}; создана конфигурация v{configuration.version}"

    @classmethod
    def _run_apply_scenario(cls, task: ScheduledTask) -> str:
        profile = DeviceConnectionManager.get_profile(task.target_device)
        if not profile:
            raise ConfigValidationError(f"No active device profile for {task.target_device.name}")
        commands = cls.preview_commands(task)
        return cls._apply_commands(profile, task, commands)

    @staticmethod
    def _run_backup(task: ScheduledTask) -> str:
        session, _profile, _check = connect_device_cli(task.target_device, verify_saved_config=True)
        try:
            current_config = session.get_running_config()
        finally:
            session.disconnect()

        configuration = ConfigurationVCS.write_backup(task.target_device, current_config, source="runtime")
        return f"Конфигурация сохранена: v{configuration.version}"

    @staticmethod
    def _run_healthcheck(task: ScheduledTask) -> str:
        try:
            session, _profile, _check = connect_device_cli(task.target_device, verify_saved_config=False)
            try:
                alive = session.is_alive()
            finally:
                session.disconnect()
            return f"Healthcheck {'OK' if alive else 'FAILED'} for {task.target_device.name}"
        except Exception as exc:
            return f"Healthcheck FAILED for {task.target_device.name}: {exc}"

    @staticmethod
    def restore_backup_to_device(backup) -> str:
        session, profile, _check = connect_device_cli(backup.device, verify_saved_config=False)
        try:
            commands = [l.strip() for l in backup.config_text.splitlines() if l.strip() and not l.strip().startswith("!")]
            valid, errors = ConfigurationValidator.validate_commands(commands)
            if not valid:
                raise ConfigValidationError("; ".join(errors))
            session.send_config_set(commands)
            running = session.get_running_config()
        finally:
            session.disconnect()

        new_configuration = ConfigurationVCS.write_backup(backup.device, running, task=backup.task, source="restore")
        return f"Активирована конфигурация v{backup.version}; текущая конфигурация сохранена как v{new_configuration.version}"

    @staticmethod
    def _reschedule_if_periodic(task: ScheduledTask) -> None:
        if not task.run_every_seconds:
            return
        task.schedule_time = timezone.now() + timedelta(seconds=task.run_every_seconds)
        task.save(update_fields=("schedule_time", "last_updated"))

    @classmethod
    def run_task(cls, task: ScheduledTask) -> None:
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
            cls._reschedule_if_periodic(task)
        except Exception as exc:
            task.retry_count += 1
            if task.retry_count <= task.max_retries:
                task.status = ScheduledTask.STATUS_PENDING
                task.result_message = f"Retry scheduled ({task.retry_count}/{task.max_retries}): {exc}"
                task.schedule_time = timezone.now() + timedelta(seconds=30)
                task.save(update_fields=("status", "result_message", "retry_count", "schedule_time", "last_updated"))
            else:
                task.save(update_fields=("retry_count", "last_updated"))
                task.update_status(ScheduledTask.STATUS_FAILED, str(exc))

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
