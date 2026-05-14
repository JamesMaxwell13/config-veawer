from __future__ import annotations

from dcim.models import Device, Interface
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .application.interface_sync import InterfaceSyncService, is_netbox_sync_suppressed
from .logging import device_log_context, logger
from .models import ConfigurationBackup


def _safe_sync_from_netbox(device: Device, origin: str) -> None:
    if is_netbox_sync_suppressed():
        return
    try:
        InterfaceSyncService.sync_from_netbox_device(device, origin=origin)
    except Exception as exc:
        logger.exception(
            "NetBox change sync failed %s origin=%s error=%s",
            device_log_context(device),
            origin,
            exc,
        )


@receiver(post_save, sender=Device)
def sync_on_device_save(sender, instance: Device, **kwargs):
    _safe_sync_from_netbox(instance, origin="device_save")


@receiver(post_save, sender=Interface)
def sync_on_interface_save(sender, instance: Interface, **kwargs):
    _safe_sync_from_netbox(instance.device, origin="interface_save")


@receiver(m2m_changed, sender=Interface.tagged_vlans.through)
def sync_on_interface_tagged_vlan_change(sender, instance: Interface, action: str, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    _safe_sync_from_netbox(instance.device, origin=f"interface_tagged_vlans:{action}")


@receiver(post_save, sender=ConfigurationBackup)
def sync_on_configuration_backup_create(sender, instance: ConfigurationBackup, created: bool, **kwargs):
    if not created:
        return
    source = str(instance.source or "").lower()
    if source in {"manual_cli", "manual_refresh"} and InterfaceSyncService.should_push_manual_backups():
        try:
            from .application.gitlab import GitLabIntegrationService

            GitLabIntegrationService.push_backup_to_gitlab(instance)
        except Exception as exc:
            logger.exception(
                "Automatic GitLab push for manual backup failed %s backup_id=%s source=%s error=%s",
                device_log_context(instance.device),
                instance.pk,
                instance.source,
                exc,
            )
