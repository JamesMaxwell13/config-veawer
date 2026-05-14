from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand

from main.infrastructure.repositories import ConfigurationRepository
from main.models import CommandTemplate


@dataclass(frozen=True)
class _TargetParam:
    entity: str
    parameter: str
    fallback_names: tuple[str, ...]


TARGETS = (
    _TargetParam("device", "hostname", ("hostname",)),
    _TargetParam("interface", "enabled", ("interface_shutdown", "interface_no_shutdown")),
    _TargetParam("interface", "description", ("interface_description", "description")),
    _TargetParam("interface", "mode", ("switchport_mode_access", "switchport_mode_trunk")),
    _TargetParam("interface", "access_vlan", ("access_vlan", "switchport_access_vlan")),
    _TargetParam("interface", "native_vlan", ("switchport_trunk_native_vlan",)),
    _TargetParam("interface", "tagged_vlans", ("switchport_trunk_allowed_vlan", "trunk_vlan")),
    _TargetParam("interface", "mtu", ("interface_mtu", "mtu")),
    _TargetParam("interface", "speed", ("speed", "interface_speed")),
    _TargetParam("interface", "duplex", ("duplex", "interface_duplex")),
    _TargetParam("interface", "poe_mode", ("interface_poe_mode", "poe_mode")),
    _TargetParam("interface", "poe_type", ("interface_poe_type", "poe_type")),
)

KNOWN_UNSUPPORTED = (
    "device.serial",
    "device.role",
    "device.platform",
    "interface.label",
    "interface.type",
    "interface.mgmt_only",
    "interface.parent",
    "interface.bridge",
    "interface.lag",
    "interface.vrf",
    "interface.wwn",
    "interface.primary_mac_address",
    "interface.qinq_svlan",
    "interface.vlan_translation_policy",
    "interface.rf_role",
    "interface.rf_channel",
    "interface.rf_channel_frequency",
    "interface.rf_channel_width",
    "interface.tx_power",
)


class Command(BaseCommand):
    help = "Report coverage of NetBox device/interface parameters by command templates."

    def add_arguments(self, parser):
        parser.add_argument("--vendor", dest="vendor", default="", help="Filter by vendor (e.g. cisco).")
        parser.add_argument("--platform", dest="platform", default="", help="Filter by platform (e.g. cisco_ios).")

    def _templates(self, vendor: str, platform: str):
        templates = ConfigurationRepository.active_templates()
        result = []
        for template in templates:
            template_vendor = str(getattr(template, "vendor", "")).lower()
            template_platform = str(getattr(template, "platform", "")).lower()
            if vendor and template_vendor != vendor:
                continue
            if platform and template_platform != platform:
                continue
            result.append(template)
        return result

    def handle(self, *args, **options):
        vendor = str(options.get("vendor") or "").strip().lower()
        platform = str(options.get("platform") or "").strip().lower()
        templates = self._templates(vendor, platform)

        self.stdout.write(self.style.SUCCESS(f"Templates in scope: {len(templates)}"))
        mapped = 0
        unresolved: list[_TargetParam] = []

        for target in TARGETS:
            explicit = [
                template
                for template in templates
                if str(getattr(template, "bound_entity_type", "") or "").lower() == target.entity
                and str(getattr(template, "bound_parameter", "") or "").lower() == target.parameter
            ]
            fallback = [
                template
                for template in templates
                if str(getattr(template, "name", "")).lower() in set(target.fallback_names)
            ]
            if explicit:
                mapped += 1
                first = explicit[0]
                self.stdout.write(
                    f"[MAPPED] {target.entity}.{target.parameter} -> "
                    f"{getattr(first, 'name', '')} (explicit binding)"
                )
                continue
            if fallback:
                mapped += 1
                first = fallback[0]
                self.stdout.write(
                    f"[MAPPED] {target.entity}.{target.parameter} -> "
                    f"{getattr(first, 'name', '')} (name fallback)"
                )
                continue
            unresolved.append(target)
            self.stdout.write(f"[UNMAPPED] {target.entity}.{target.parameter}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Mapped: {mapped}/{len(TARGETS)}"))
        if unresolved:
            self.stdout.write(self.style.WARNING("Unmapped parameters:"))
            for target in unresolved:
                self.stdout.write(f" - {target.entity}.{target.parameter}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Not linked by design in current implementation:"))
        for field_name in KNOWN_UNSUPPORTED:
            self.stdout.write(f" - {field_name}")

        custom_qs = CommandTemplate.objects.all()
        if vendor:
            custom_qs = custom_qs.filter(vendor__iexact=vendor)
        if platform:
            custom_qs = custom_qs.filter(platform__iexact=platform)
        self.stdout.write(f"Database templates in scope: {custom_qs.count()}")
