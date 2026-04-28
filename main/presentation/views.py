from django.contrib import messages
from dcim.models import Device
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponseBadRequest
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from netbox.views import generic

from . import filtersets, forms, tables
from ..application.backups import ConfigurationBackupService
from ..application.tasks import TaskExecutor
from ..application.uml import UMLConfigurationService
from ..models import (
    CommandTemplate,
    ConfigurationBackup,
    DeviceCredential,
    DevicePlatformProfile,
    NetworkTask,
    ScheduledTask,
    UMLConfiguration,
)


class DeviceCredentialListView(generic.ObjectListView):
    queryset = DeviceCredential.objects.all()
    table = tables.DeviceCredentialTable
    filterset = filtersets.DeviceCredentialFilterSet


class DeviceCredentialView(generic.ObjectView):
    queryset = DeviceCredential.objects.all()


class DeviceCredentialEditView(generic.ObjectEditView):
    queryset = DeviceCredential.objects.all()
    form = forms.DeviceCredentialForm


class DeviceCredentialDeleteView(generic.ObjectDeleteView):
    queryset = DeviceCredential.objects.all()


class DevicePlatformProfileListView(generic.ObjectListView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    table = tables.DevicePlatformProfileTable
    filterset = filtersets.DevicePlatformProfileFilterSet


class DevicePlatformProfileView(generic.ObjectView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")


class DevicePlatformProfileEditView(generic.ObjectEditView):
    queryset = DevicePlatformProfile.objects.select_related("device", "credential")
    form = forms.DevicePlatformProfileForm


class DevicePlatformProfileDeleteView(generic.ObjectDeleteView):
    queryset = DevicePlatformProfile.objects.all()


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


class ConfigurationBackupRestoreView(View):
    def post(self, request, pk):
        backup = get_object_or_404(ConfigurationBackup, pk=pk)
        try:
            result = TaskExecutor.restore_backup_to_device(backup)
            messages.success(request, result)
        except Exception as exc:
            messages.error(request, f"Backup restore failed: {exc}")
        return redirect(reverse("plugins:main:configurationbackup", kwargs={"pk": backup.pk}))


class ConfigurationVersionListView(TemplateView):
    template_name = "main/configuration_versions.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device = get_object_or_404(Device, pk=kwargs["device_id"])
        versions = ConfigurationBackup.objects.filter(device=device).order_by("-version")
        context["device"] = device
        context["versions"] = versions
        return context


class ConfigurationVersionDiffView(TemplateView):
    template_name = "main/configuration_diff.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device = get_object_or_404(Device, pk=kwargs["device_id"])
        v_from = self.request.GET.get("from")
        v_to = self.request.GET.get("to")
        if not v_from or not v_to:
            context["error"] = "Set query params: from and to"
            context["diff"] = []
            context["device"] = device
            return context
        b_from = get_object_or_404(ConfigurationBackup, device=device, version=int(v_from))
        b_to = get_object_or_404(ConfigurationBackup, device=device, version=int(v_to))
        context["device"] = device
        context["from_backup"] = b_from
        context["to_backup"] = b_to
        context["diff"] = ConfigurationBackupService.compare_versions(b_from.config_text, b_to.config_text)
        return context


class ScheduledTaskListView(generic.ObjectListView):
    queryset = ScheduledTask.objects.select_related("target_device", "task")
    table = tables.ScheduledTaskTable
    filterset = filtersets.ScheduledTaskFilterSet


class ScheduledTaskView(generic.ObjectView):
    queryset = ScheduledTask.objects.select_related("target_device", "task")


class ScheduledTaskEditView(generic.ObjectEditView):
    queryset = ScheduledTask.objects.select_related("target_device", "task")
    form = forms.ScheduledTaskForm


class ScheduledTaskDeleteView(generic.ObjectDeleteView):
    queryset = ScheduledTask.objects.all()


class ScheduledTaskRunNowView(View):
    def post(self, request, pk):
        confirm = request.POST.get("confirm_create_version")
        if confirm != "on":
            return HttpResponseBadRequest("Version creation confirmation is required.")
        task = get_object_or_404(ScheduledTask, pk=pk)
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
