from django.utils.translation import gettext as _

from netbox.plugins.navigation import PluginMenu, PluginMenuButton, PluginMenuItem

menu_items = (
    PluginMenuItem(
        link="plugins:main:deviceplatformprofile_list",
        link_text="Devices",
        buttons=(
            PluginMenuButton(
                link="plugins:main:deviceplatformprofile_add",
                title="Add device profile",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:configurationbackup_list",
        link_text="Configurations",
        buttons=(
            PluginMenuButton(
                link="plugins:main:configurationbackup_add",
                title="Create configuration",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:scheduledtask_list",
        link_text="Task scheduler",
        buttons=(
            PluginMenuButton(
                link="plugins:main:scheduledtask_add",
                title="Add task",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:commandtemplate_list",
        link_text="Command templates",
        buttons=(
            PluginMenuButton(
                link="plugins:main:commandtemplate_add",
                title="Add command template",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
    PluginMenuItem(
        link="plugins:main:devicecredential_list",
        link_text="Credentials",
        buttons=(
            PluginMenuButton(
                link="plugins:main:devicecredential_add",
                title="Add credential",
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
                title="Add GitLab integration",
                icon_class="mdi mdi-plus-thick",
            ),
        ),
    ),
)

menu = PluginMenu(
    label=_("Config Weaver"),
    icon_class="mdi mdi-router-network",
    groups=(("Device Management", menu_items),),
)
