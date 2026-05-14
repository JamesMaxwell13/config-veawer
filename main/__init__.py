from netbox.plugins import PluginConfig


class NetBoxConfigWeaverConfig(PluginConfig):
    name = "main"
    verbose_name = "config-weaver"
    description = "config-weaver: network configuration management plugin for NetBox"
    version = "0.2.0"
    author = "Andrew Gorokh"
    author_email = "jamesclerkmaxxwel13@gmail.com"
    base_url = "config-weaver"
    template_extensions = "template_content.template_extensions"
    required_settings = ["secret_key"]
    default_settings = {
        "vcs_repo_path": "",
        "secret_key": "",
        "scheduler_max_workers": 8,
        "auto_sync_on_netbox_change": True,
        "auto_sync_from_config": True,
        "sync_debounce_seconds": 3,
        "auto_push_manual_backups": True,
        "credential_reveal_max_attempts": 5,
        "credential_reveal_window_seconds": 300,
    }
    min_version = "4.0.0"
    max_version = "4.99.99"

    def ready(self):
        super().ready()
        from .application.security import validate_security_settings
        from . import signals  # noqa: F401

        validate_security_settings()


config = NetBoxConfigWeaverConfig
