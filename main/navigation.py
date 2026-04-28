from django.utils.translation import gettext as _

from netbox.plugins.navigation import PluginMenu, PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:main:device_list",
        link_text="Устройства",
        buttons=(
            PluginMenuButton(
                link="plugins:main:device_add",
                title="Добавить устройство",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:configuration_list",
        link_text="Конфигурации",
        buttons=(
            PluginMenuButton(
                link="plugins:main:configuration_add",
                title="Создать конфигурацию",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:scheduledtask_list",
        link_text="Планировщик задач",
        buttons=(
            PluginMenuButton(
                link="plugins:main:scheduledtask_add",
                title="Новая задача",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:devicecredential_list",
        link_text="Учетные данные",
        buttons=(
            PluginMenuButton(
                link="plugins:main:devicecredential_add",
                title="Добавить учетные данные",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
)

menu = PluginMenu(
    label=_("Config Weaver"),
    icon_class="mdi mdi-router-network",
    groups=(("Управление устройствами", menu_items),),
)
