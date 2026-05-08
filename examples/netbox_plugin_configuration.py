"""
Example NetBox configuration.py fragment for config-weaver.

Copy the relevant values into NetBox's configuration.py. This file is not
loaded by the plugin automatically; NetBox passes values through PLUGINS_CONFIG.
"""

import os


PLUGINS = [
    # Django app name from main/__init__.py.
    # The public URL base is still /plugins/config-weaver/ because the plugin
    # config defines base_url = "config-weaver".
    "main",
]


def _int_env(name, default):
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default
    return int(raw_value)


PLUGINS_CONFIG = {
    "main": {
        # Required. Used to encrypt DeviceCredential.password and enable_secret.
        # Keep this value stable after credentials are created.
        "secret_key": os.getenv(
            "CONFIG_WEAVER_SECRET_KEY",
            "replace-with-a-long-random-plugin-secret",
        ),

        # Optional. Git repository for saved configuration versions.
        # If omitted, the plugin falls back to MEDIA_ROOT/config_weaver_repo.
        "vcs_repo_path": os.getenv(
            "CONFIG_WEAVER_VCS_REPO",
            "/home/andrew/bsuir/diploma/config-weaver-vcs",
        ),

        # Optional. Maximum number of scheduled tasks executed in parallel.
        "scheduler_max_workers": _int_env("CONFIG_WEAVER_SCHEDULER_MAX_WORKERS", 8),
    }
}
