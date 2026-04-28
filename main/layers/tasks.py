from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from ..models import DevicePlatformProfile, NetworkTask, ScheduledTask, UMLConfiguration
from .configuration import CommandGenerator, ConfigurationRepository, ConfigurationValidator, NetworkPlanParser, ConfigValidationError
from .network import connect_device_cli, DeviceConnectionManager
from .vcs import ConfigurationVCS


class TaskExecutor:
    @staticmethod
    def preview_commands(task: ScheduledTask) -> list[str]:
        if not task.task:
            raise ConfigValidationError("Task is required for apply_scenario task")

        profile = DeviceConnectionManager.get_profile(task.target_device)
        if not profile:
            raise ConfigValidationError(f"No active device profile for {task.target_device.name}")

        scenario_stamp = int(task.task.last_updated.timestamp()) if task.task.last_updated else 0
        cache_key = f"cw:preview:{task.pk}:{scenario_stamp}:{profile.pk}"
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

        backup = ConfigurationVCS.write_backup(task.target_device, running, task=task.task, source="runtime")
        return f"Scenario applied via {profile.vendor}/{profile.platform}; backup version={backup.version}"

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

        backup = ConfigurationVCS.write_backup(task.target_device, current_config, source="runtime")
        return f"Backup created version={backup.version}"

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

        new_backup = ConfigurationVCS.write_backup(backup.device, running, task=backup.task, source="restore")
        return f"Restore applied from backup v{backup.version}; new backup v{new_backup.version}"

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
    def run_due_tasks(cls) -> int:
        due = ScheduledTask.objects.filter(schedule_time__lte=timezone.now()).exclude(status=ScheduledTask.STATUS_RUNNING)
        count = 0
        for task in due:
            if task.is_due():
                cls.run_task(task)
                count += 1
        return count


class UMLConfigurationService:
    @staticmethod
    def calculate_checksum(source_text: str) -> str:
        import hashlib

        return hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    @classmethod
    def save_with_checksum(cls, uml: UMLConfiguration) -> UMLConfiguration:
        uml.checksum = cls.calculate_checksum(uml.source_text)
        uml.save()
        return uml

    @staticmethod
    def render_preview(uml: UMLConfiguration) -> str:
        if uml.diagram_type == UMLConfiguration.TYPE_PLANTUML:
            return (
                "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='120'>"
                "<rect x='1' y='1' width='1198' height='118' fill='#f8fafc' stroke='#94a3b8'/>"
                "<text x='20' y='35' font-size='18' fill='#0f172a'>PlantUML source stored</text>"
                "<text x='20' y='65' font-size='14' fill='#334155'>Use external PlantUML renderer for full output.</text>"
                "</svg>"
            )
        escaped = uml.source_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        title = "Mermaid source preview" if uml.diagram_type == UMLConfiguration.TYPE_MERMAID else "JSON source preview"
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='320'>"
            "<rect x='1' y='1' width='1198' height='318' fill='#f8fafc' stroke='#94a3b8'/>"
            f"<text x='20' y='30' font-size='16' fill='#0f172a'>{title}</text>"
            "<foreignObject x='20' y='45' width='1160' height='250'>"
            "<div xmlns='http://www.w3.org/1999/xhtml' style='font-family:monospace;white-space:pre-wrap;color:#334155'>"
            f"{escaped}</div></foreignObject></svg>"
        )
