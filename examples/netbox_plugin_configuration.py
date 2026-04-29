"""
Example NetBox configuration fragment for config-weaver.

Copy the relevant values into NetBox's configuration.py. The plugin does not
load this file directly; NetBox passes these settings through PLUGINS_CONFIG.
"""

PLUGINS = [
    "main",
]

PLUGINS_CONFIG = {
    "main": {
        # Required. Used to encrypt DeviceCredential.password and enable_secret.
        "secret_key": "replace-with-a-long-random-plugin-secret",

        # Optional. Git repository for saved configuration versions.
        # If omitted, the plugin falls back to MEDIA_ROOT/config_weaver_repo.
        "vcs_repo_path": "/home/andrew/bsuir/diploma/config-weaver-vcs",

        # Optional. Maximum number of scheduled tasks executed in parallel.
        "scheduler_max_workers": 8,
    }
}
