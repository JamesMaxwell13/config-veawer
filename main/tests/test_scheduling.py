from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from main.application.tasks import TaskExecutor
from main.models import ScheduledTask


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
