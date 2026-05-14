from __future__ import annotations

from dataclasses import dataclass
import re

from dcim.choices import InterfaceDuplexChoices, InterfaceModeChoices, InterfaceTypeChoices
from dcim.models import Device, Interface
from django.core.management.base import BaseCommand, CommandError
from ipam.models import VLAN
from netmiko import ConnectHandler

from main.application.interface_sync import suppress_netbox_sync
from main.models import DevicePlatformProfile


@dataclass
class ParsedInterface:
    name: str
    type: str
    enabled: bool = True
    description: str = ""
    mtu: int | None = None
    speed: int | None = None
    duplex: str | None = None
    mode: str | None = None
    access_vlan: int | None = None
    native_vlan: int | None = None
    tagged_vlans: set[int] | None = None
    poe_mode: str | None = None


def _infer_interface_type(name: str) -> str:
    lowered = name.strip().lower()
    if "." in lowered:
        return InterfaceTypeChoices.TYPE_VIRTUAL
    if lowered.startswith("port-channel"):
        return InterfaceTypeChoices.TYPE_LAG
    if lowered.startswith(("loopback", "vlan", "tunnel", "dialer", "bdi", "nve", "virtual-template", "virtual-access")):
        return InterfaceTypeChoices.TYPE_VIRTUAL
    if lowered.startswith(("tengigabitethernet", "te")):
        return InterfaceTypeChoices.TYPE_10GE_FIXED
    if lowered.startswith(("fastethernet", "fa")):
        return InterfaceTypeChoices.TYPE_100ME_FIXED
    if lowered.startswith(("gigabitethernet", "gi", "ethernet", "eth")):
        return InterfaceTypeChoices.TYPE_1GE_FIXED
    return InterfaceTypeChoices.TYPE_VIRTUAL


def _normalize_interface_name(name: str) -> str:
    value = re.sub(r"\s+", "", str(name).strip().lower())
    aliases = (
        ("gigabitethernet", "gi"),
        ("fastethernet", "fa"),
        ("tengigabitethernet", "te"),
        ("ethernet", "eth"),
        ("port-channel", "po"),
    )
    for full, short in aliases:
        if value.startswith(full):
            return short + value[len(full):]
    return value


def _parse_speed_to_kbps(value: str) -> int | None:
    token = value.strip().lower()
    if token == "auto":
        return None
    try:
        return int(token) * 1000
    except ValueError:
        return None


def _parse_vlan_set(value: str) -> set[int]:
    if value.strip().lower() == "all":
        return set()
    result: set[int] = set()
    for token in value.split(","):
        item = token.strip()
        if not item:
            continue
        if "-" in item:
            left, right = item.split("-", 1)
            try:
                start = int(left)
                end = int(right)
            except ValueError:
                continue
            if start <= end:
                result.update(range(start, end + 1))
            continue
        try:
            result.add(int(item))
        except ValueError:
            continue
    return result


def _parse_running_config_interfaces(config_text: str) -> list[ParsedInterface]:
    parsed: list[ParsedInterface] = []
    current: ParsedInterface | None = None

    for raw_line in config_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("interface "):
            if current is not None:
                parsed.append(current)
            name = stripped.split(None, 1)[1]
            current = ParsedInterface(name=name, type=_infer_interface_type(name))
            continue
        if current is None:
            continue
        if stripped == "!":
            parsed.append(current)
            current = None
            continue
        if not stripped:
            continue

        if stripped.startswith("description "):
            current.description = stripped[len("description ") :]
            continue
        if stripped == "shutdown":
            current.enabled = False
            continue
        if stripped == "no shutdown":
            current.enabled = True
            continue
        if stripped.startswith("mtu "):
            try:
                current.mtu = int(stripped.split()[1])
            except (IndexError, ValueError):
                pass
            continue
        if stripped.startswith("speed "):
            tokens = stripped.split(maxsplit=1)
            if len(tokens) == 2:
                current.speed = _parse_speed_to_kbps(tokens[1])
            continue
        if stripped.startswith("duplex "):
            tokens = stripped.split(maxsplit=1)
            if len(tokens) == 2:
                duplex = tokens[1].strip().lower()
                if duplex in {InterfaceDuplexChoices.DUPLEX_AUTO, InterfaceDuplexChoices.DUPLEX_FULL, InterfaceDuplexChoices.DUPLEX_HALF}:
                    current.duplex = duplex
            continue
        if stripped == "switchport mode access":
            current.mode = InterfaceModeChoices.MODE_ACCESS
            continue
        if stripped == "switchport mode trunk":
            current.mode = InterfaceModeChoices.MODE_TAGGED
            continue
        if stripped.startswith("switchport access vlan "):
            match = re.search(r"(\d+)$", stripped)
            if match:
                current.access_vlan = int(match.group(1))
                current.mode = InterfaceModeChoices.MODE_ACCESS
            continue
        if stripped.startswith("switchport trunk native vlan "):
            match = re.search(r"(\d+)$", stripped)
            if match:
                current.native_vlan = int(match.group(1))
                if not current.mode:
                    current.mode = InterfaceModeChoices.MODE_TAGGED
            continue
        if stripped.startswith("switchport trunk allowed vlan "):
            value = stripped.split("switchport trunk allowed vlan ", 1)[1].strip()
            if value.lower() == "all":
                current.mode = InterfaceModeChoices.MODE_TAGGED_ALL
                current.tagged_vlans = set()
            else:
                current.mode = InterfaceModeChoices.MODE_TAGGED
                current.tagged_vlans = _parse_vlan_set(value)
            continue
        if stripped.startswith("power inline "):
            power_mode = stripped.split("power inline ", 1)[1].strip().split()[0].lower()
            if power_mode in {"auto", "static"}:
                current.poe_mode = "pse"
            elif power_mode in {"never"}:
                current.poe_mode = None

    if current is not None:
        parsed.append(current)
    return parsed


def _ensure_vlan(device: Device, vid: int) -> VLAN:
    return VLAN.objects.filter(site__in=[device.site, None], vid=vid).order_by("pk").first() or VLAN.objects.create(
        site=device.site,
        vid=vid,
        name=f"VLAN{vid}",
    )


class Command(BaseCommand):
    help = "Import interfaces from a device running-config via SSH and upsert dcim.Interface records."

    def add_arguments(self, parser):
        parser.add_argument("--device", default="R1", help="NetBox device name.")
        parser.add_argument("--host", default="", help="SSH host/IP (defaults to profile management IP).")
        parser.add_argument("--username", default="", help="SSH username override.")
        parser.add_argument("--password", default="", help="SSH password override.")
        parser.add_argument("--port", type=int, default=22, help="SSH TCP port.")
        parser.add_argument("--timeout", type=int, default=30, help="SSH timeout in seconds.")
        parser.add_argument("--platform", default="", help="Netmiko platform override (defaults to profile platform).")

    def handle(self, *args, **options):
        device_name = str(options["device"]).strip()
        device = Device.objects.filter(name=device_name).first()
        if not device:
            raise CommandError(f"Device '{device_name}' not found.")

        profile = DevicePlatformProfile.objects.filter(device=device, enabled=True).first()
        platform = str(options.get("platform") or getattr(profile, "platform", "") or "cisco_ios")
        host = str(options.get("host") or getattr(profile, "management_ip", "") or "").strip()
        if not host and device.primary_ip4:
            host = str(device.primary_ip4.address).split("/")[0]
        if not host:
            raise CommandError("SSH host is not set and device/profile has no management IP.")

        username = str(options.get("username") or "")
        password = str(options.get("password") or "")
        if not username or not password:
            if not profile:
                raise CommandError("No active profile and no explicit --username/--password.")
            username = profile.credential.username
            password = profile.credential.password_plain

        session = ConnectHandler(
            device_type=platform,
            host=host,
            username=username,
            password=password,
            port=int(options["port"]),
            timeout=int(options["timeout"]),
        )
        try:
            running_config = session.send_command("show running-config")
        finally:
            session.disconnect()

        parsed = _parse_running_config_interfaces(running_config)
        if not parsed:
            raise CommandError("No interfaces parsed from running-config.")

        created = 0
        updated = 0

        with suppress_netbox_sync():
            for parsed_item in parsed:
                interface = Interface.objects.filter(device=device, name=parsed_item.name).first()
                was_created = False
                if interface is None:
                    normalized = _normalize_interface_name(parsed_item.name)
                    for candidate in Interface.objects.filter(device=device):
                        if _normalize_interface_name(candidate.name) == normalized:
                            interface = candidate
                            break
                if interface is None:
                    interface = Interface.objects.create(
                        device=device,
                        name=parsed_item.name,
                        type=parsed_item.type,
                    )
                    was_created = True
                elif interface.name != parsed_item.name:
                    interface.name = parsed_item.name
                    interface.save(update_fields=("name", "last_updated"))
                changes = []
                if interface.type != parsed_item.type:
                    interface.type = parsed_item.type
                    changes.append("type")
                if interface.enabled != parsed_item.enabled:
                    interface.enabled = parsed_item.enabled
                    changes.append("enabled")
                if interface.description != parsed_item.description:
                    interface.description = parsed_item.description
                    changes.append("description")
                if interface.mtu != parsed_item.mtu:
                    interface.mtu = parsed_item.mtu
                    changes.append("mtu")
                if interface.speed != parsed_item.speed:
                    interface.speed = parsed_item.speed
                    changes.append("speed")
                if interface.duplex != parsed_item.duplex:
                    interface.duplex = parsed_item.duplex
                    changes.append("duplex")

                if interface.mode != parsed_item.mode:
                    interface.mode = parsed_item.mode
                    changes.append("mode")

                if parsed_item.poe_mode != interface.poe_mode and parsed_item.poe_mode in {"pd", "pse", None}:
                    interface.poe_mode = parsed_item.poe_mode
                    changes.append("poe_mode")

                if parsed_item.mode == InterfaceModeChoices.MODE_ACCESS:
                    new_vlan = _ensure_vlan(device, parsed_item.access_vlan) if parsed_item.access_vlan else None
                    if interface.untagged_vlan_id != getattr(new_vlan, "pk", None):
                        interface.untagged_vlan = new_vlan
                        changes.append("untagged_vlan")

                if parsed_item.mode in {InterfaceModeChoices.MODE_TAGGED, InterfaceModeChoices.MODE_TAGGED_ALL} and parsed_item.native_vlan:
                    native_vlan = _ensure_vlan(device, parsed_item.native_vlan)
                    if interface.untagged_vlan_id != native_vlan.pk:
                        interface.untagged_vlan = native_vlan
                        changes.append("untagged_vlan")

                if changes:
                    interface.save(update_fields=tuple(sorted(set(changes))) + ("last_updated",))
                    if was_created:
                        created += 1
                    else:
                        updated += 1
                elif was_created:
                    created += 1

                if parsed_item.mode == InterfaceModeChoices.MODE_TAGGED and parsed_item.tagged_vlans is not None:
                    desired = [_ensure_vlan(device, vid) for vid in sorted(parsed_item.tagged_vlans)]
                    current = set(interface.tagged_vlans.values_list("vid", flat=True))
                    new_set = {item.vid for item in desired}
                    if current != new_set:
                        interface.tagged_vlans.set(desired)
                        if not was_created and not changes:
                            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Imported interfaces for {device.name}: created={created}, updated={updated}, total_parsed={len(parsed)}"))
