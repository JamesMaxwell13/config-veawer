from __future__ import annotations

import re

from django.conf import settings
from django.urls import re_path

from .consumers import DeviceTerminalConsumer


base_path = settings.BASE_PATH.strip("/")
prefix = f"{re.escape(base_path)}/" if base_path else ""

websocket_urlpatterns = [
    re_path(
        rf"^{prefix}ws/plugins/config-weaver/devices/(?P<pk>\d+)/terminal/$",
        DeviceTerminalConsumer.as_asgi(),
    ),
]
