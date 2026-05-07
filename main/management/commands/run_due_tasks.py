from django.core.management.base import BaseCommand

from main.application.tasks import TaskExecutor


class Command(BaseCommand):
    help = "Run due config-weaver scheduled tasks"

    def handle(self, *args, **options):
        TaskExecutor.run_due_tasks()
