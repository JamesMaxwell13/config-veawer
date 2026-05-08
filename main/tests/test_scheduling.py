from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from main.application.tasks import TaskExecutor
from main.domain.configuration import ConfigValidationError
from main.infrastructure.vcs import ConfigurationVCS
from main.models import ConfigurationBackup, DeviceCredential, DevicePlatformProfile, ScheduledTask


def create_device(name="scheduled-r1"):
    manufacturer = Manufacturer.objects.create(name=f"{name} manufacturer", slug=f"{name}-manufacturer")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model=f"{name} type", slug=f"{name}-type")
    role = DeviceRole.objects.create(name=f"{name} role", slug=f"{name}-role")
    site = Site.objects.create(name=f"{name} site", slug=f"{name}-site")
    return Device.objects.create(site=site, device_type=device_type, role=role, name=name)


class ScheduledTaskLogicTests(TestCase):
    def test_pending_due(self):
        task = ScheduledTask(
            task_name="t1",
            task_type=ScheduledTask.TYPE_BACKUP,
            schedule_time=timezone.now() - timedelta(seconds=1),
            status=ScheduledTask.STATUS_PENDING,
        )
        self.assertTrue(task.is_due())

    def test_success_without_periodicity_not_due(self):
        task = ScheduledTask(
            task_name="t2",
            task_type=ScheduledTask.TYPE_BACKUP,
            schedule_time=timezone.now() - timedelta(seconds=1),
            status=ScheduledTask.STATUS_SUCCESS,
            run_every_seconds=None,
        )
        self.assertFalse(task.is_due())

    def test_success_periodic_due(self):
        task = ScheduledTask(
            task_name="t3",
            task_type=ScheduledTask.TYPE_BACKUP,
            schedule_time=timezone.now() - timedelta(seconds=1),
            status=ScheduledTask.STATUS_SUCCESS,
            run_every_seconds=60,
        )
        self.assertTrue(task.is_due())

    @override_settings(PLUGINS_CONFIG={"main": {"scheduler_max_workers": 4}})
    def test_scheduler_max_workers_from_plugin_config(self):
        self.assertEqual(TaskExecutor.scheduler_max_workers(), 4)

    @override_settings(PLUGINS_CONFIG={"main": {"scheduler_max_workers": "invalid"}})
    def test_scheduler_max_workers_falls_back_for_invalid_value(self):
        self.assertEqual(TaskExecutor.scheduler_max_workers(), 8)

    @override_settings(PLUGINS_CONFIG={"main": {"scheduler_max_workers": 0}})
    def test_scheduler_max_workers_has_minimum_one(self):
        self.assertEqual(TaskExecutor.scheduler_max_workers(), 1)

    @override_settings(PLUGINS_CONFIG={"main": {"scheduler_max_workers": 3}})
    def test_run_due_tasks_submits_due_tasks_to_thread_pool(self):
        due_task = ScheduledTask(
            pk=101,
            task_name="t4",
            task_type=ScheduledTask.TYPE_BACKUP,
            schedule_time=timezone.now() - timedelta(seconds=1),
            status=ScheduledTask.STATUS_PENDING,
        )
        future = MagicMock()
        queryset = MagicMock()
        queryset.exclude.return_value = [due_task]

        with (
            patch("main.application.tasks.ScheduledTask.objects.filter", return_value=queryset),
            patch("main.application.tasks.ThreadPoolExecutor") as executor_cls,
            patch.object(TaskExecutor, "_run_task_by_id") as run_task_by_id,
        ):
            executor = executor_cls.return_value.__enter__.return_value
            executor.submit.return_value = future

            executed = TaskExecutor.run_due_tasks()

        self.assertEqual(executed, 1)
        executor_cls.assert_called_once_with(max_workers=3)
        executor.submit.assert_called_once_with(run_task_by_id, due_task.pk)
        future.result.assert_called_once_with()

    def test_run_due_tasks_command_does_not_print_executed_count(self):
        stdout = StringIO()

        with patch.object(TaskExecutor, "run_due_tasks", return_value=0):
            call_command("run_due_tasks", stdout=stdout)

        output = stdout.getvalue()
        self.assertEqual(output, "")
        self.assertNotIn("Executed tasks: 0", output)

    def test_apply_scenario_requires_inline_yaml_task(self):
        task = ScheduledTask(
            task_name="empty-yaml",
            task_type=ScheduledTask.TYPE_APPLY_SCENARIO,
            schedule_time=timezone.now(),
            task="",
        )

        with self.assertRaisesMessage(ConfigValidationError, "YAML task is required"):
            TaskExecutor.preview_commands(task)

    def test_apply_scenario_creates_runtime_backup_without_pre_apply(self):
        device = create_device()
        credential = DeviceCredential.objects.create(
            name="scheduled-credential",
            username="admin",
            password="password",
        )
        profile = DevicePlatformProfile.objects.create(
            device=device,
            credential=credential,
            vendor=DevicePlatformProfile.VENDOR_CISCO,
            platform=DevicePlatformProfile.PLATFORM_CISCO_IOS,
            management_ip="192.0.2.10",
            enabled=True,
        )
        task = ScheduledTask.objects.create(
            task_name="GitLab apply R1",
            task_type=ScheduledTask.TYPE_APPLY_SCENARIO,
            target_device=device,
            schedule_time=timezone.now(),
            status=ScheduledTask.STATUS_PENDING,
            task="hostname scheduled-r1",
        )
        session = MagicMock()
        session.get_running_config.side_effect = [
            "hostname scheduled-r1-before",
            "hostname scheduled-r1-after",
        ]

        with TemporaryDirectory() as tmpdir:
            with (
                patch("main.application.tasks.connect_device_cli", return_value=(session, profile, {"checked": False})),
                patch.object(ConfigurationVCS, "repo_path", return_value=Path(tmpdir)),
                patch("main.infrastructure.vcs.subprocess.run"),
                patch("main.infrastructure.vcs.subprocess.check_output", return_value=b"abc123\n"),
            ):
                result = TaskExecutor._apply_commands(profile, task, ["hostname scheduled-r1-after"])

        self.assertIn("Сценарий применен", result)
        session.send_config_set.assert_called_once_with(["hostname scheduled-r1-after"])
        self.assertEqual(ConfigurationBackup.objects.filter(device=device).count(), 1)
        self.assertFalse(ConfigurationBackup.objects.filter(device=device, source="pre_apply").exists())
        runtime_backup = ConfigurationBackup.objects.get(device=device, source="runtime")
        self.assertIsNone(runtime_backup.task)
