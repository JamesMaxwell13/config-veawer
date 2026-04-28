from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

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
