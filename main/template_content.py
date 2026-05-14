from __future__ import annotations

from netbox.plugins.templates import PluginTemplateExtension

from .models import DevicePlatformProfile


class DeviceConfigWeaverButtons(PluginTemplateExtension):
    models = ["dcim.device"]

    def buttons(self):
        profile = (
            DevicePlatformProfile.objects.filter(device=self.context["object"], enabled=True)
            .select_related("device")
            .first()
        )
        if not profile:
            return ""
        return self.render(
            "main/inc/device_config_weaver_buttons.html",
            {"profile": profile},
        )


class ConfigWeaverAssets(PluginTemplateExtension):
    def head(self):
        return self.render("main/inc/yaml_highlight_assets.html")


template_extensions = [ConfigWeaverAssets, DeviceConfigWeaverButtons]
