from django.utils.translation import gettext as _

from netbox.plugins.navigation import PluginMenu, PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:main:deviceplatformprofile_list",
        link_text="Устройства",
        buttons=(
            PluginMenuButton(
                link="plugins:main:deviceplatformprofile_add",
                title="Добавить устройство",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:configurationbackup_list",
        link_text="Конфигурации",
        buttons=(
            PluginMenuButton(
                link="plugins:main:configurationbackup_add",
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
        link="plugins:main:commandtemplate_list",
        link_text="Шаблоны команд",
        buttons=(
            PluginMenuButton(
                link="plugins:main:commandtemplate_add",
                title="Добавить шаблон команд",
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
    PluginMenuItem(
        link="plugins:main:gitlabintegration_list",
        link_text="GitLab",
        buttons=(
            PluginMenuButton(
                link="plugins:main:gitlabintegration_add",
                title="Добавить GitLab integration",
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
