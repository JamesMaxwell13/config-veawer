from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from main.application.tasks import TaskExecutor
from main.infrastructure.network import ConnectionSession
from main.infrastructure.vcs import ConfigurationVCS
from main.models import ConfigurationBackup, ScheduledTask


LOGGER_NAME = "netbox.plugins.config_weaver"


def create_device(name="router-1"):
    manufacturer = Manufacturer.objects.create(name=f"{name} manufacturer", slug=f"{name}-manufacturer")
    device_type = DeviceType.objects.create(manufacturer=manufacturer, model=f"{name} type", slug=f"{name}-type")
    role = DeviceRole.objects.create(name=f"{name} role", slug=f"{name}-role")
    site = Site.objects.create(name=f"{name} site", slug=f"{name}-site")
    return Device.objects.create(site=site, device_type=device_type, role=role, name=name)


class ConnectionLoggingTests(SimpleTestCase):
    def test_send_config_set_logs_metadata_without_command_body(self):
        session = ConnectionSession()
        session.backend = "netmiko"
        session.platform = "cisco_ios"
        session.session = MagicMock()
        session.session.send_config_set.return_value = "configured"
        session.session.send_command_timing.return_value = "saved"

        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            session.send_config_set(["username admin password secret-value"])

        output = "\n".join(logs.output)
        self.assertIn("command_count=2", output)
        self.assertNotIn("secret-value", output)
        self.assertNotIn("username admin password", output)
        session.session.send_config_set.assert_called_once_with(["username admin password secret-value"])
        session.session.send_command_timing.assert_called_once_with("write memory")

    def test_send_config_set_does_not_duplicate_save_command(self):
        session = ConnectionSession()
        session.backend = "netmiko"
        session.platform = "cisco_ios"
        session.session = MagicMock()
        session.session.send_config_set.return_value = "configured"
        session.session.send_command_timing.return_value = "saved"

        session.send_config_set(["hostname router-1", "write memory"])

        session.session.send_config_set.assert_called_once_with(["hostname router-1"])
        session.session.send_command_timing.assert_called_once_with("write memory")

    @patch("main.infrastructure.network.paramiko.SSHClient")
    def test_paramiko_fallback_uses_hostname_argument(self, ssh_client):
        client = ssh_client.return_value
        session = ConnectionSession()
        session.platform = "cisco_ios"

        session._connect_paramiko(
            {
                "host": "192.0.2.10",
                "username": "admin",
                "password": "password",
                "port": 22,
                "timeout": 10,
            }
        )

        client.connect.assert_called_once_with(
            hostname="192.0.2.10",
            username="admin",
            password="password",
            port=22,
            timeout=10,
        )


class ScheduledTaskLoggingTests(TestCase):
    def test_run_task_logs_start_and_success(self):
        device = create_device()
        task = ScheduledTask.objects.create(
            task_name="backup-now",
            task_type=ScheduledTask.TYPE_BACKUP,
            target_device=device,
            schedule_time=timezone.now(),
        )

        with (
            patch.object(TaskExecutor, "_run_backup", return_value="done"),
            self.assertLogs(LOGGER_NAME, level="INFO") as logs,
        ):
            TaskExecutor.run_task(task)

        output = "\n".join(logs.output)
        self.assertIn("Executing task", output)
        self.assertIn("Scheduled task completed", output)
        self.assertIn("task=backup-now", output)
        self.assertIn("device=router-1", output)

    def test_run_task_logs_failure_and_marks_task_failed(self):
        device = create_device()
        task = ScheduledTask.objects.create(
            task_name="bad-backup",
            task_type=ScheduledTask.TYPE_BACKUP,
            target_device=device,
            schedule_time=timezone.now(),
        )

        with (
            patch.object(TaskExecutor, "_run_backup", side_effect=RuntimeError("connection failed")),
            self.assertLogs(LOGGER_NAME, level="INFO") as logs,
        ):
            TaskExecutor.run_task(task)

        task.refresh_from_db()
        output = "\n".join(logs.output)
        self.assertEqual(task.status, ScheduledTask.STATUS_FAILED)
        self.assertIn("Scheduled task failed", output)
        self.assertIn("Scheduled task marked failed", output)
        self.assertIn("connection failed", output)


class ConfigurationVCSLoggingTests(TestCase):
    def test_write_backup_logs_version_metadata_without_config_body(self):
        device = create_device()

        with TemporaryDirectory() as tmpdir:
            with (
                patch.object(ConfigurationVCS, "repo_path", return_value=Path(tmpdir)),
                patch("main.infrastructure.vcs.subprocess.run"),
                patch("main.infrastructure.vcs.subprocess.check_output", return_value=b"abc123\n"),
                self.assertLogs(LOGGER_NAME, level="INFO") as logs,
            ):
                backup = ConfigurationVCS.write_backup(
                    device=device,
                    config_text="username admin password secret-value",
                    source="runtime",
                )

        output = "\n".join(logs.output)
        self.assertEqual(backup.version, 1)
        self.assertEqual(backup.commit_hash, "abc123")
        self.assertIn("Configuration backup created", output)
        self.assertIn("version=1", output)
        self.assertIn("commit=abc123", output)
        self.assertNotIn("secret-value", output)

    def test_restore_logs_without_new_version_when_running_config_matches(self):
        device = create_device()
        backup = ConfigurationBackup.objects.create(
            device=device,
            version=1,
            version_name="v1",
            config_text="hostname router-1",
            source="runtime",
            config_checksum="old",
        )
        session = MagicMock()
        session.get_running_config.return_value = "hostname router-1"

        with (
            patch("main.application.tasks.connect_device_cli", return_value=(session, None, {"checked": False})),
            patch("main.application.tasks.ConfigurationVCS.write_backup") as write_backup,
            self.assertLogs(LOGGER_NAME, level="INFO") as logs,
        ):
            TaskExecutor.restore_backup_to_device(backup)

        output = "\n".join(logs.output)
        write_backup.assert_not_called()
        self.assertIn("Restoring configuration backup", output)
        self.assertIn("Configuration backup restored without new version", output)
        self.assertIn("source_version=1", output)
