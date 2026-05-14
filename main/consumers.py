from __future__ import annotations

import threading
import time

from channels.generic.websocket import JsonWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

from .application.terminal import DeviceTerminalService
from .logging import device_log_context, logger
from .models import DevicePlatformProfile


class DeviceTerminalConsumer(JsonWebsocketConsumer):
    permission_required = "main.change_deviceplatformprofile"

    def connect(self):
        self.profile = None
        self.terminal = None
        self.reader_stop = threading.Event()
        self.reader_thread = None
        self.send_lock = threading.Lock()

        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            self.close(code=4401)
            return

        try:
            self.profile = DevicePlatformProfile.objects.select_related("device", "credential").get(
                pk=self.scope["url_route"]["kwargs"]["pk"]
            )
        except ObjectDoesNotExist:
            self.close(code=4404)
            return

        if not user.has_perm(self.permission_required, self.profile):
            logger.warning(
                "Manual terminal access denied %s user=%s",
                device_log_context(self.profile.device, self.profile),
                user,
            )
            self.close(code=4403)
            return

        self.accept()
        self._safe_send_json({"type": "status", "state": "connecting"})
        try:
            self.terminal = DeviceTerminalService(self.profile, user)
            initial_output = self.terminal.open()
        except Exception as exc:
            logger.exception(
                "Manual terminal connection failed %s user=%s",
                device_log_context(self.profile.device, self.profile),
                user,
            )
            self._safe_send_json({"type": "error", "message": str(exc)})
            self.close(code=4500)
            return

        self._safe_send_json({"type": "status", "state": "connected"})
        if initial_output:
            self._safe_send_json({"type": "output", "data": initial_output})
        self.reader_thread = threading.Thread(target=self._read_terminal_output, daemon=True)
        self.reader_thread.start()

    def receive_json(self, content, **kwargs):
        if not self.terminal:
            self._safe_send_json({"type": "error", "message": "Terminal is not connected"})
            return

        message_type = content.get("type")
        if message_type == "input":
            data = content.get("data", "")
            if not isinstance(data, str):
                self._safe_send_json({"type": "error", "message": "Input data must be a string"})
                return
            try:
                self.terminal.send_input(data)
            except Exception as exc:
                logger.exception(
                    "Manual terminal input failed %s user=%s",
                    device_log_context(self.profile.device, self.profile),
                    self.scope.get("user"),
                )
                self._safe_send_json({"type": "error", "message": str(exc)})
        elif message_type == "disconnect":
            self.close(code=1000)
        else:
            self._safe_send_json({"type": "error", "message": f"Unsupported message type: {message_type}"})

    def disconnect(self, code):
        self.reader_stop.set()
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1)
        if self.terminal:
            self.terminal.close(create_backup=True)

    def _read_terminal_output(self):
        while not self.reader_stop.is_set():
            try:
                output = self.terminal.read_available() if self.terminal else ""
            except Exception as exc:
                logger.exception(
                    "Manual terminal read failed %s user=%s",
                    device_log_context(self.profile.device, self.profile),
                    self.scope.get("user"),
                )
                self._safe_send_json({"type": "error", "message": str(exc)})
                return
            if output:
                self._safe_send_json({"type": "output", "data": output})
            time.sleep(0.1)

    def _safe_send_json(self, content):
        try:
            with self.send_lock:
                self.send_json(content)
        except Exception:
            logger.exception("Failed to send terminal websocket message")
