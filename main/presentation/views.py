from django.contrib import messages
from dcim.models import Device
from django.contrib.auth import update_session_auth_hash
from django.conf import settings
from django.utils.html import conditional_escape
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponseBadRequest
from django.urls import reverse
from django.views import View
from django.views.generic import FormView, TemplateView
from django_tables2 import RequestConfig
from netbox.views import generic
from utilities.views import ObjectPermissionRequiredMixin, ViewTab, register_model_view
from urllib.parse import urlencode
import yaml

from . import filtersets, forms, tables
from ..application.backups import ConfigurationService
from ..application.configuration_yaml import ConfigurationYamlService
from ..application.gitlab import GitLabIntegrationService
from ..application.tasks import TaskExecutor
from ..application.uml import UMLConfigurationService
from ..domain.configuration import CommandGenerator
from ..infrastructure.network import connect_device_cli
from ..infrastructure.vcs import ConfigurationVCS
from ..logging import device_log_context, logger
from ..models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    GitLabConfigMapping,
    GitLabIntegration,
    GitLabSyncLog,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)


def configuration_backup_to_yaml(backup):
    if ConfigurationYamlService.is_yaml_config(backup.config_text):
        return backup.config_text
    payload = {
        "device": backup.device.name,
        "version": backup.version,
        "version_name": backup.version_name,
        "created": backup.created.isoformat() if backup.created else None,
        "source": backup.source,
        "commit_hash": backup.commit_hash,
        "config_checksum": backup.config_checksum,
        "redacted": backup.redacted,
        "config": backup.config_text,
    }
    return ConfigurationYamlService.dump_yaml(payload)


class DeviceCredentialListView(generic.ObjectListView):
    queryset = DeviceCredential.objects.all()
    table = tables.DeviceCredentialTable
    filterset = filtersets.DeviceCredentialFilterSet


class DeviceCredentialView(generic.ObjectView):
    queryset = DeviceCredential.objects.all()


class DeviceCredentialRevealView(FormView):
    template_name = "main/devicecredential_reveal.html"
    form_class = forms.CredentialRevealForm

    def dispatch(self, request, *args, **kwargs):
        self.credential = get_object_or_404(DeviceCredential, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["credential"] = self.credential
        return context

    def form_valid(self, form):
        username = form.cleaned_data["account_username"]
        password = form.cleaned_data["account_password"]
        if username != self.request.user.get_username():
            form.add_error("account_username", "Неверный логин учетной записи NetBox.")
            return self.form_invalid(form)
        if not self.request.user.check_password(password):
            form.add_error("account_password", "Неверный пароль учетной записи NetBox.")
            return self.form_invalid(form)
        update_session_auth_hash(self.request, self.request.user)
        context = self.get_context_data(form=form)
        context["reveal_success"] = True
        context["revealed_password"] = self.credential.password_plain
        context["revealed_enable_secret"] = self.credential.enable_secret_plain
        return self.render_to_response(context)


class DeviceCredentialEditView(generic.ObjectEditView):
    queryset = DeviceCredential.objects.all()
    form = forms.DeviceCredentialForm


class DeviceCredentialDeleteView(generic.ObjectDeleteView):
    queryset = DeviceCredential.objects.all()


class DeviceCredentialBulkEditView(generic.BulkEditView):
    queryset = DeviceCredential.objects.all()
    table = tables.DeviceCredentialTable
    filterset = filtersets.DeviceCredentialFilterSet
    form = forms.DeviceCredentialBulkEditForm


class DeviceCredentialBulkDeleteView(generic.BulkDeleteView):
    queryset = DeviceCredential.objects.all()
    table = tables.DeviceCredentialTable
    filterset = filtersets.DeviceCredentialFilterSet


class DevicePlatformProfileListView(generic.ObjectListView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    table = tables.DevicePlatformProfileTable
    filterset = filtersets.DevicePlatformProfileFilterSet


class DevicePlatformProfileView(generic.ObjectView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")

    def get_extra_context(self, request, instance):
        command_template_url = (
            reverse("plugins:main:commandtemplate_list")
            + "?"
            + urlencode({"vendor": instance.vendor, "platform": instance.platform})
        )
        return {
            "scheduled_tasks": ScheduledTask.objects.filter(target_device=instance.device).order_by("-schedule_time")[:10],
            "command_template_url": command_template_url,
        }


@register_model_view(DevicePlatformProfile, "versions", path="versions")
class DevicePlatformProfileVersionsView(generic.ObjectView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    template_name = "main/configuration_versions.html"
    tab = ViewTab(
        label="Версии конфигураций",
        badge=lambda obj: ConfigurationBackup.objects.filter(device=obj.device).count(),
        weight=500,
    )
    actions = ()

    def get_extra_context(self, request, instance):
        versions = ConfigurationBackup.objects.filter(device=instance.device).order_by("-version")
        return {
            "device": instance.device,
            "versions": versions,
            "current_version": versions.first(),
            "diff_url": reverse("plugins:main:deviceplatformprofile_versions_diff", kwargs={"pk": instance.pk}),
        }


class DevicePlatformProfileEditView(generic.ObjectEditView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    form = forms.DevicePlatformProfileForm


class DevicePlatformProfileDeleteView(generic.ObjectDeleteView):
    queryset = DevicePlatformProfile.objects.all()


class DevicePlatformProfileBulkEditView(generic.BulkEditView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    table = tables.DevicePlatformProfileTable
    filterset = filtersets.DevicePlatformProfileFilterSet
    form = forms.DevicePlatformProfileBulkEditForm


class DevicePlatformProfileBulkDeleteView(generic.BulkDeleteView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    table = tables.DevicePlatformProfileTable
    filterset = filtersets.DevicePlatformProfileFilterSet


class GitLabIntegrationListView(generic.ObjectListView):
    queryset = GitLabIntegration.objects.all()
    table = tables.GitLabIntegrationTable
    filterset = filtersets.GitLabIntegrationFilterSet


class GitLabIntegrationView(generic.ObjectView):
    queryset = GitLabIntegration.objects.all()

    def get_extra_context(self, request, instance):
        mapping_table = tables.GitLabConfigMappingTable(
            GitLabConfigMapping.objects.filter(integration=instance).select_related(
                "integration",
                "device",
                "configuration_backup",
            ),
            prefix="mapping-",
        )
        sync_log_table = tables.GitLabSyncLogTable(
            GitLabSyncLog.objects.filter(integration=instance).select_related(
                "integration",
                "mapping",
                "device",
                "configuration_backup",
                "task",
            ),
            prefix="log-",
        )
        RequestConfig(request, paginate={"per_page": 10}).configure(mapping_table)
        RequestConfig(request, paginate={"per_page": 10}).configure(sync_log_table)
        return {
            "mapping_table": mapping_table,
            "sync_log_table": sync_log_table,
        }


class GitLabIntegrationEditView(generic.ObjectEditView):
    queryset = GitLabIntegration.objects.all()
    form = forms.GitLabIntegrationForm


class GitLabIntegrationDeleteView(generic.ObjectDeleteView):
    queryset = GitLabIntegration.objects.all()


class GitLabIntegrationActionView(ObjectPermissionRequiredMixin, View):
    queryset = GitLabIntegration.objects.all()
    action = ""

    def get_required_permission(self):
        return "main.change_gitlabintegration"

    def post(self, request, pk):
        integration = get_object_or_404(self.queryset, pk=pk)
        try:
            if self.action == "test":
                GitLabIntegrationService.client_for(integration).test_connection(
                    integration.project_id,
                    integration.branch,
                )
                messages.success(request, "GitLab connection succeeded.")
            elif self.action == "sync":
                results = GitLabIntegrationService.sync_from_gitlab(integration)
                messages.success(request, f"GitLab sync completed: {len(results)} file(s).")
            elif self.action == "push":
                results = GitLabIntegrationService.push_to_gitlab(integration)
                messages.success(request, f"GitLab push completed: {len(results)} configuration(s).")
            elif self.action == "rebuild":
                count = GitLabIntegrationService.rebuild_paths(integration)
                messages.success(request, f"Rebuilt {count} GitLab path(s).")
            else:
                return HttpResponseBadRequest("Unsupported GitLab action.")
        except Exception as exc:
            messages.error(request, f"GitLab action failed: {exc}")
            logger.exception("GitLab action failed action=%s integration_id=%s", self.action, integration.pk)
        return redirect(integration.get_absolute_url())


class GitLabConfigMappingListView(generic.ObjectListView):
    queryset = GitLabConfigMapping.objects.select_related("integration", "device", "configuration_backup")
    table = tables.GitLabConfigMappingTable
    filterset = filtersets.GitLabConfigMappingFilterSet


class GitLabConfigMappingView(generic.ObjectView):
    queryset = GitLabConfigMapping.objects.select_related("integration", "device", "configuration_backup")


class GitLabConfigMappingEditView(generic.ObjectEditView):
    queryset = GitLabConfigMapping.objects.select_related("integration", "device", "configuration_backup")
    form = forms.GitLabConfigMappingForm


class GitLabConfigMappingDeleteView(generic.ObjectDeleteView):
    queryset = GitLabConfigMapping.objects.all()


class GitLabSyncLogListView(generic.ObjectListView):
    queryset = GitLabSyncLog.objects.select_related("integration", "mapping", "device", "configuration_backup", "task")
    table = tables.GitLabSyncLogTable
    filterset = filtersets.GitLabSyncLogFilterSet


class GitLabSyncLogView(generic.ObjectView):
    queryset = GitLabSyncLog.objects.select_related("integration", "mapping", "device", "configuration_backup", "task")


class DevicePlatformProfileCLIView(View):
    def post(self, request, pk):
        profile = get_object_or_404(DevicePlatformProfile.objects.select_related("device"), pk=pk)
        form = forms.DeviceCommandForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Проверьте список команд.")
            return redirect(profile.get_absolute_url())

        commands = [line.strip() for line in form.cleaned_data["commands"].splitlines() if line.strip()]
        if not commands:
            messages.error(request, "Введите хотя бы одну команду.")
            return redirect(profile.get_absolute_url())

        logger.info(
            "Manual CLI command execution requested %s command_count=%s user=%s",
            device_log_context(profile.device, profile),
            len(commands),
            request.user,
        )
        session, _profile, _check = connect_device_cli(profile.device, verify_saved_config=False)
        try:
            output = session.send_config_set(commands)
            running_config = session.get_running_config()
        finally:
            session.disconnect()

        configuration = ConfigurationVCS.write_backup(
            profile.device,
            running_config,
            source="manual_cli",
        )
        logger.info(
            "Manual CLI command execution completed "
            "%s command_count=%s configuration_version=%s backup_id=%s user=%s",
            device_log_context(profile.device, profile),
            len(commands),
            configuration.version,
            configuration.pk,
            request.user,
        )
        messages.success(
            request,
            (
                "Команды выполнены. "
                f"Создана конфигурация v{configuration.version}. "
                f"Вывод: {output[:300]}"
            ),
        )
        return redirect(configuration.get_absolute_url())


class DevicePlatformProfileRefreshConfigView(ObjectPermissionRequiredMixin, View):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")

    def get_required_permission(self):
        return "main.change_deviceplatformprofile"

    def post(self, request, pk):
        profile = get_object_or_404(self.queryset, pk=pk)
        try:
            result = ConfigurationService.refresh_device_config(profile.device)
        except Exception as exc:
            messages.error(request, f"Не удалось получить конфигурацию: {exc}")
            logger.exception(
                "Manual device configuration refresh failed %s user=%s",
                device_log_context(profile.device, profile),
                request.user,
            )
            return redirect(profile.get_absolute_url())

        backup = result["backup"]
        if result["changed"]:
            messages.success(request, f"Конфигурация обновлена. Создана версия v{backup.version}.")
        else:
            messages.success(request, f"Конфигурация не изменилась. Текущая версия v{backup.version}.")
        return redirect(backup.get_absolute_url())


class DevicePlatformProfileTerminalView(ObjectPermissionRequiredMixin, TemplateView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    template_name = "main/deviceplatformprofile_terminal.html"

    def get_required_permission(self):
        return "main.change_deviceplatformprofile"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_object_or_404(self.queryset, pk=kwargs["pk"])
        base_path = settings.BASE_PATH.strip("/")
        base_url = f"/{base_path}/" if base_path else "/"
        context["object"] = profile
        context["terminal_ws_path"] = (
            f"{base_url}ws/plugins/config-weaver/devices/{profile.pk}/terminal/"
        )
        return context


class CommandTemplateListView(generic.ObjectListView):
    queryset = CommandTemplate.objects.all()
    table = tables.CommandTemplateTable
    filterset = filtersets.CommandTemplateFilterSet


class CommandTemplateView(generic.ObjectView):
    queryset = CommandTemplate.objects.all()


class CommandTemplateEditView(generic.ObjectEditView):
    queryset = CommandTemplate.objects.all()
    form = forms.CommandTemplateForm


class CommandTemplateDeleteView(generic.ObjectDeleteView):
    queryset = CommandTemplate.objects.all()


class CommandTemplateBulkEditView(generic.BulkEditView):
    queryset = CommandTemplate.objects.all()
    table = tables.CommandTemplateTable
    filterset = filtersets.CommandTemplateFilterSet
    form = forms.CommandTemplateBulkEditForm


class CommandTemplateBulkDeleteView(generic.BulkDeleteView):
    queryset = CommandTemplate.objects.all()
    table = tables.CommandTemplateTable
    filterset = filtersets.CommandTemplateFilterSet


class CommandTemplatePreviewView(FormView):
    template_name = "main/commandtemplate_preview.html"
    form_class = forms.CommandTemplatePreviewForm

    def dispatch(self, request, *args, **kwargs):
        self.template = get_object_or_404(CommandTemplate, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"params": "interface: GigabitEthernet0/1\nip: 10.0.0.1\nmask: 255.255.255.0\n"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["template"] = self.template
        context.setdefault("commands", [])
        return context

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        try:
            rendered = self.template.render(form.cleaned_data["params"])
            context["commands"] = CommandGenerator.split_rendered_commands(rendered)
        except KeyError as exc:
            form.add_error("params", f"Не хватает параметра: {exc}")
            return self.form_invalid(form)
        return self.render_to_response(context)


class NetworkTaskListView(generic.ObjectListView):
    queryset = NetworkTask.objects.all()
    table = tables.NetworkTaskTable
    filterset = filtersets.NetworkTaskFilterSet


class NetworkTaskView(generic.ObjectView):
    queryset = NetworkTask.objects.all()


class NetworkTaskEditView(generic.ObjectEditView):
    queryset = NetworkTask.objects.all()
    form = forms.NetworkTaskForm


class NetworkTaskDeleteView(generic.ObjectDeleteView):
    queryset = NetworkTask.objects.all()


class ConfigurationBackupListView(generic.ObjectListView):
    queryset = ConfigurationBackup.objects.select_related("device", "task")
    table = tables.ConfigurationBackupTable
    filterset = filtersets.ConfigurationBackupFilterSet


class ConfigurationBackupView(generic.ObjectView):
    queryset = ConfigurationBackup.objects.select_related("device", "task")

    def get_extra_context(self, request, instance):
        return {
            "yaml_text": configuration_backup_to_yaml(instance),
            "profile": DevicePlatformProfile.objects.filter(device=instance.device).first(),
        }


class ConfigurationBackupYAMLView(ObjectPermissionRequiredMixin, TemplateView):
    queryset = ConfigurationBackup.objects.select_related("device", "task")
    template_name = "main/configurationbackup_yaml.html"

    def get_required_permission(self):
        return "main.view_configurationbackup"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        backup = get_object_or_404(self.queryset, pk=kwargs["pk"])
        context["object"] = backup
        context["yaml_text"] = configuration_backup_to_yaml(backup)
        return context


class ConfigurationBackupEditView(generic.ObjectEditView):
    queryset = ConfigurationBackup.objects.select_related("device", "task")
    form = forms.ConfigurationBackupForm


class ConfigurationBackupDeleteView(generic.ObjectDeleteView):
    queryset = ConfigurationBackup.objects.select_related("device", "task")


class ConfigurationBackupBulkEditView(generic.BulkEditView):
    queryset = ConfigurationBackup.objects.select_related("device", "task")
    table = tables.ConfigurationBackupTable
    filterset = filtersets.ConfigurationBackupFilterSet
    form = forms.ConfigurationBackupBulkEditForm


class ConfigurationBackupBulkDeleteView(generic.BulkDeleteView):
    queryset = ConfigurationBackup.objects.select_related("device", "task")
    table = tables.ConfigurationBackupTable
    filterset = filtersets.ConfigurationBackupFilterSet


class ConfigurationBackupRestoreView(View):
    def post(self, request, pk):
        backup = get_object_or_404(ConfigurationBackup, pk=pk)
        logger.info(
            "Configuration restore requested %s backup_id=%s source_version=%s user=%s",
            device_log_context(backup.device),
            backup.pk,
            backup.version,
            request.user,
        )
        try:
            result = TaskExecutor.restore_backup_to_device(backup)
            messages.success(request, result)
            logger.info(
                "Configuration restore request completed %s backup_id=%s user=%s",
                device_log_context(backup.device),
                backup.pk,
                request.user,
            )
        except Exception as exc:
            messages.error(request, f"Не удалось отправить конфигурацию на устройство: {exc}")
            logger.exception(
                "Configuration restore request failed %s backup_id=%s user=%s",
                device_log_context(backup.device),
                backup.pk,
                request.user,
            )
        profile = DevicePlatformProfile.objects.filter(device=backup.device).first()
        if profile:
            return redirect(profile.get_absolute_url())
        return redirect(backup.get_absolute_url())


def _device_has_config_weaver_profile(device):
    return DevicePlatformProfile.objects.filter(device=device, enabled=True).exists()


@register_model_view(Device, "configurations", path="config-weaver-configurations")
class DeviceConfigurationsView(generic.ObjectView):
    queryset = Device.objects.all()
    template_name = "main/device_configurations.html"
    tab = ViewTab(
        label="Конфигурации",
        visible=_device_has_config_weaver_profile,
        badge=lambda obj: ConfigurationBackup.objects.filter(device=obj).count(),
        weight=2150,
        hide_if_empty=False,
    )
    actions = ()

    def get_extra_context(self, request, instance):
        configurations = list(ConfigurationBackup.objects.filter(device=instance).order_by("-version"))
        current = configurations[0] if configurations else None
        profile = DevicePlatformProfile.objects.filter(device=instance, enabled=True).first()
        return {
            "profile": profile,
            "current_configuration": current,
            "previous_configurations": configurations[1:],
            "current_yaml": configuration_backup_to_yaml(current) if current else "",
        }


class ConfigurationBackupRefreshView(ObjectPermissionRequiredMixin, View):
    queryset = ConfigurationBackup.objects.select_related("device", "task")

    def get_required_permission(self):
        return "main.change_configurationbackup"

    def post(self, request, pk):
        backup = get_object_or_404(self.queryset, pk=pk)
        try:
            result = ConfigurationService.refresh_device_config(
                backup.device,
                compare_to=backup,
                source="manual_refresh",
            )
        except Exception as exc:
            messages.error(request, f"Не удалось проверить конфигурацию: {exc}")
            logger.exception(
                "Manual configuration backup refresh failed %s backup_id=%s user=%s",
                device_log_context(backup.device),
                backup.pk,
                request.user,
            )
            return redirect(backup.get_absolute_url())

        refreshed = result["backup"]
        if result["changed"]:
            messages.warning(
                request,
                f"Конфигурация на устройстве отличается. Создана новая версия v{refreshed.version}.",
            )
            return redirect(refreshed.get_absolute_url())
        messages.success(request, f"Конфигурация на устройстве совпадает с v{backup.version}.")
        return redirect(backup.get_absolute_url())


class DevicePlatformProfileVersionDiffView(TemplateView):
    template_name = "main/configuration_diff.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_object_or_404(DevicePlatformProfile.objects.select_related("device"), pk=kwargs["pk"])
        device = profile.device
        v_from = self.request.GET.get("from")
        v_to = self.request.GET.get("to")
        context["device"] = device
        context["profile"] = profile
        if not v_from or not v_to:
            context["error"] = "Set query params: from and to"
            context["diff"] = []
            return context
        b_from = get_object_or_404(ConfigurationBackup, device=device, version=int(v_from))
        b_to = get_object_or_404(ConfigurationBackup, device=device, version=int(v_to))
        context["from_backup"] = b_from
        context["to_backup"] = b_to
        context["diff"] = [
            _format_diff_line(line)
            for line in ConfigurationService.compare_versions(b_from.config_text, b_to.config_text)
        ]
        return context


def _format_diff_line(line):
    css_class = ""
    if line.startswith("+") and not line.startswith("+++"):
        css_class = "text-success"
    elif line.startswith("-") and not line.startswith("---"):
        css_class = "text-danger"
    return {"text": conditional_escape(line), "class": css_class}


class ScheduledTaskListView(generic.ObjectListView):
    queryset = ScheduledTask.objects.select_related("target_device")
    table = tables.ScheduledTaskTable
    filterset = filtersets.ScheduledTaskFilterSet


class ScheduledTaskView(generic.ObjectView):
    queryset = ScheduledTask.objects.select_related("target_device")


class ScheduledTaskEditView(generic.ObjectEditView):
    queryset = ScheduledTask.objects.select_related("target_device")
    form = forms.ScheduledTaskForm


class ScheduledTaskDeleteView(generic.ObjectDeleteView):
    queryset = ScheduledTask.objects.all()


class ScheduledTaskBulkEditView(generic.BulkEditView):
    queryset = ScheduledTask.objects.select_related("target_device")
    table = tables.ScheduledTaskTable
    filterset = filtersets.ScheduledTaskFilterSet
    form = forms.ScheduledTaskBulkEditForm


class ScheduledTaskBulkDeleteView(generic.BulkDeleteView):
    queryset = ScheduledTask.objects.select_related("target_device")
    table = tables.ScheduledTaskTable
    filterset = filtersets.ScheduledTaskFilterSet


class ScheduledTaskRunNowView(View):
    def post(self, request, pk):
        confirm = request.POST.get("confirm_create_version")
        if confirm != "on":
            return HttpResponseBadRequest("Version creation confirmation is required.")
        task = get_object_or_404(ScheduledTask, pk=pk)
        logger.info(
            "Manual scheduled task run requested task=%s task_id=%s user=%s",
            task.task_name,
            task.pk,
            request.user,
        )
        TaskExecutor.run_task(task)
        task.refresh_from_db()
        if task.status == ScheduledTask.STATUS_SUCCESS:
            messages.success(request, f"Task '{task.task_name}' executed successfully")
        else:
            messages.error(request, f"Task '{task.task_name}' failed: {task.result_message}")
        return redirect(reverse("plugins:main:scheduledtask", kwargs={"pk": task.pk}))


class ScheduledTaskPreviewView(TemplateView):
    template_name = "main/scheduledtask_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = get_object_or_404(ScheduledTask, pk=kwargs["pk"])
        context["task"] = task
        try:
            context["commands"] = TaskExecutor.preview_commands(task)
            context["errors"] = []
        except Exception as exc:
            context["commands"] = []
            context["errors"] = [str(exc)]
        return context


class UMLConfigurationListView(generic.ObjectListView):
    queryset = UMLConfiguration.objects.select_related("task", "device")
    table = tables.UMLConfigurationTable
    filterset = filtersets.UMLConfigurationFilterSet


class UMLConfigurationView(generic.ObjectView):
    queryset = UMLConfiguration.objects.select_related("task", "device")


class UMLConfigurationEditView(generic.ObjectEditView):
    queryset = UMLConfiguration.objects.select_related("task", "device")
    form = forms.UMLConfigurationForm


class UMLConfigurationDeleteView(generic.ObjectDeleteView):
    queryset = UMLConfiguration.objects.all()


class UMLConfigurationRenderView(View):
    def post(self, request, pk):
        uml = get_object_or_404(UMLConfiguration, pk=pk)
        try:
            uml.rendered_svg = UMLConfigurationService.render_preview(uml)
            UMLConfigurationService.save_with_checksum(uml)
            messages.success(request, "UML preview rendered successfully")
        except Exception as exc:
            messages.error(request, f"UML render failed: {exc}")
        return redirect(reverse("plugins:main:umlconfiguration", kwargs={"pk": uml.pk}))


class UMLConfigurationPreviewView(TemplateView):
    template_name = "main/umlconfiguration_preview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        uml = get_object_or_404(UMLConfiguration, pk=kwargs["pk"])
        context["uml"] = uml
        context["rendered_svg"] = uml.rendered_svg or UMLConfigurationService.render_preview(uml)
        return context
