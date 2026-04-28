from netbox.plugins import PluginConfig


class NetBoxConfigWeaverConfig(PluginConfig):
    name = "main"
    verbose_name = "config-weaver"
    description = "config-weaver: модуль управления конфигурациями сетевого оборудования для NetBox"
    version = "0.2.0"
    author = "Andrew Gorokh"
    author_email = "jamesclerkmaxxwel13@gmail.com"
    base_url = "config-weaver"
    required_settings = ["secret_key"]
    default_settings = {
        "vcs_repo_path": "",
        "secret_key": "",
    }
    min_version = "4.0.0"
    max_version = "4.99.99"


config = NetBoxConfigWeaverConfig
