from django.utils.translation import gettext as _

from netbox.plugins.navigation import PluginMenu, PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:main:deviceplatformprofile_list",
        link_text="Устройства Cisco/D-Link",
        buttons=(
            PluginMenuButton(
                link="plugins:main:deviceplatformprofile_add",
                title="Добавить профиль",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:networktask_list",
        link_text="Сетевые задачи",
        buttons=(
            PluginMenuButton(
                link="plugins:main:networktask_add",
                title="Добавить задачу",
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
        link="plugins:main:commandtemplate_list",
        link_text="Шаблоны команд",
        buttons=(
            PluginMenuButton(
                link="plugins:main:commandtemplate_add",
                title="Добавить шаблон",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:configurationbackup_list",
        link_text="Бэкапы конфигураций",
    ),
    PluginMenuItem(
        link="plugins:main:umlconfiguration_list",
        link_text="UML-конфигурации",
        buttons=(
            PluginMenuButton(
                link="plugins:main:umlconfiguration_add",
                title="Добавить UML",
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
    groups=(("Управление конфигурацией", menu_items),),
)
