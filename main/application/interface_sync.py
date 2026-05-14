from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import re
import uuid
from typing import Any

from dcim.choices import InterfaceDuplexChoices, InterfaceModeChoices, InterfacePoEModeChoices, InterfacePoETypeChoices
from dcim.models import Device, Interface
from django.conf import settings
from django.core.cache import cache
from ipam.models import VLAN

from ..application.configuration_yaml import ConfigurationYamlService
from ..application.tasks import TaskExecutor
from ..infrastructure.repositories import ConfigurationRepository
from ..logging import device_log_context, logger
from ..models import ConfigurationBackup, DevicePlatformProfile, ParameterSyncLog


_SYNC_SILENCED: ContextVar[bool] = ContextVar("cw_sync_silenced", default=False)


def _plugin_cfg() -> dict[str, Any]:
    return getattr(settings, "PLUGINS_CONFIG", {}).get("main", {})


def _bool_cfg(key: str, default: bool) -> bool:
    return bool(_plugin_cfg().get(key, default))


def _int_cfg(key: str, default: int) -> int:
    raw = _plugin_cfg().get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _template_params(template: Any) -> tuple[str, ...]:
    params = getattr(template, "params", None)
    if isinstance(params, (list, tuple)):
        return tuple(str(item) for item in params)
    body = str(getattr(template, "command_body", ""))
    return tuple(dict.fromkeys(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", body)))


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


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_vlan_set(value: Any) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, int):
        return {value}
    text = str(value).strip().lower()
    if not text or text == "all":
        return set()
    values: set[int] = set()
    for token in text.split(","):
        item = token.strip()
        if not item:
            continue
        if "-" in item:
            left, right = item.split("-", 1)
            start = _parse_int(left)
            end = _parse_int(right)
            if start is None or end is None or start > end:
                continue
            values.update(range(start, end + 1))
            continue
        parsed = _parse_int(item)
        if parsed is not None:
            values.add(parsed)
    return values


@dataclass(frozen=True)
class _TemplateRef:
    name: str
    operation_type: str
    params: tuple[str, ...]
    bound_entity_type: str
    bound_parameter: str
    bound_direction: str
    binding_priority: int


class _TemplateResolver:
    def __init__(self, profile: DevicePlatformProfile) -> None:
        self._templates = []
        for template in ConfigurationRepository.active_templates():
            if str(getattr(template, "vendor", "")).lower() != profile.vendor.lower():
                continue
            if str(getattr(template, "platform", "")).lower() != profile.platform.lower():
                continue
            self._templates.append(
                _TemplateRef(
                    name=str(getattr(template, "name", "")),
                    operation_type=str(getattr(template, "operation_type", "custom")),
                    params=_template_params(template),
                    bound_entity_type=str(getattr(template, "bound_entity_type", "") or "").lower(),
                    bound_parameter=str(getattr(template, "bound_parameter", "") or "").lower(),
                    bound_direction=str(getattr(template, "bound_direction", "both") or "both").lower(),
                    binding_priority=int(getattr(template, "binding_priority", 100) or 100),
                )
            )
        self._by_name: dict[str, list[_TemplateRef]] = {}
        self._by_binding: dict[tuple[str, str], list[_TemplateRef]] = {}
        for template in self._templates:
            self._by_name.setdefault(template.name.lower(), []).append(template)
            if template.bound_entity_type and template.bound_parameter:
                key = (template.bound_entity_type, template.bound_parameter)
                self._by_binding.setdefault(key, []).append(template)

        for key in self._by_binding:
            self._by_binding[key].sort(key=lambda item: (item.binding_priority, item.name))

    def select(self, names: list[str], required_params: tuple[str, ...] = ()) -> _TemplateRef | None:
        required = set(required_params)
        for candidate in names:
            entries = self._by_name.get(candidate.lower()) or []
            for entry in entries:
                if required.issubset(set(entry.params)):
                    return entry
        return None

    def has(self, names: list[str], required_params: tuple[str, ...] = ()) -> bool:
        return self.select(names, required_params) is not None

    def select_bound(
        self,
        entity_type: str,
        parameter: str,
        *,
        direction: str,
        required_params: tuple[str, ...] = (),
    ) -> _TemplateRef | None:
        required = set(required_params)
        key = (entity_type.lower(), parameter.lower())
        entries = self._by_binding.get(key) or []
        for entry in entries:
            if entry.bound_direction not in {"both", direction.lower()}:
                continue
            if required.issubset(set(entry.params)):
                return entry
        return None

    def semantics_for_operation(self, name: str, operation_type: str) -> tuple[str, str] | None:
        entries = self._by_name.get(name.lower()) or []
        for entry in entries:
            if entry.operation_type.lower() != operation_type.lower():
                continue
            if entry.bound_entity_type and entry.bound_parameter:
                return entry.bound_entity_type, entry.bound_parameter
        return None


@contextmanager
def suppress_netbox_sync() -> Any:
    token = _SYNC_SILENCED.set(True)
    try:
        yield
    finally:
        _SYNC_SILENCED.reset(token)


def is_netbox_sync_suppressed() -> bool:
    return bool(_SYNC_SILENCED.get())


class InterfaceSyncService:
    DIRECTION_NETBOX_TO_CONFIG = "netbox_to_config"
    DIRECTION_CONFIG_TO_NETBOX = "config_to_netbox"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    @classmethod
    def should_sync_on_netbox_change(cls) -> bool:
        return _bool_cfg("auto_sync_on_netbox_change", True)

    @classmethod
    def should_sync_from_config(cls) -> bool:
        return _bool_cfg("auto_sync_from_config", True)

    @classmethod
    def should_push_manual_backups(cls) -> bool:
        return _bool_cfg("auto_push_manual_backups", True)

    @classmethod
    def debounce_seconds(cls) -> int:
        return _int_cfg("sync_debounce_seconds", 3)

    @classmethod
    def _log(
        cls,
        *,
        device: Device,
        direction: str,
        status: str,
        origin: str,
        message: str,
        changed_fields: list[str] | None = None,
        backup: ConfigurationBackup | None = None,
        correlation_id: str = "",
    ) -> None:
        ParameterSyncLog.objects.create(
            device=device,
            configuration_backup=backup,
            direction=direction,
            status=status,
            origin=origin,
            changed_fields=changed_fields or [],
            message=message,
            correlation_id=correlation_id or "",
        )

    @classmethod
    def _build_operation(cls, template: _TemplateRef, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": template.name,
            "operation_type": template.operation_type,
            "params": params,
        }

    @classmethod
    def _speed_to_cli(cls, speed_kbps: int | None) -> str | None:
        if not speed_kbps:
            return None
        if speed_kbps % 1000 == 0:
            return str(speed_kbps // 1000)
        return str(speed_kbps)

    @classmethod
    def _speed_to_netbox(cls, value: Any) -> int | None:
        parsed = _parse_int(value)
        if parsed is None:
            return None
        if parsed <= 100000:
            return parsed * 1000
        return parsed

    @classmethod
    def _interfaces_for_device(cls, device: Device) -> list[Interface]:
        return list(
            Interface.objects.filter(device=device)
            .select_related("untagged_vlan")
            .prefetch_related("tagged_vlans")
            .order_by("name")
        )

    @classmethod
    def _render_netbox_operations(cls, device: Device, profile: DevicePlatformProfile) -> list[dict[str, Any]]:
        resolver = _TemplateResolver(profile)
        operations: list[dict[str, Any]] = []

        hostname_template = resolver.select_bound(
            "device",
            "hostname",
            direction="nb_to_cfg",
            required_params=("hostname",),
        ) or resolver.select(["hostname"], ("hostname",))
        if hostname_template and device.name:
            operations.append(cls._build_operation(hostname_template, {"hostname": device.name}))

        for interface in cls._interfaces_for_device(device):
            iface = interface.name

            description_template = resolver.select_bound(
                "interface",
                "description",
                direction="nb_to_cfg",
                required_params=("interface", "description"),
            ) or resolver.select(["interface_description", "description"], ("interface", "description"))
            if description_template and interface.description:
                operations.append(
                    cls._build_operation(
                        description_template,
                        {"interface": iface, "description": interface.description},
                    )
                )

            shutdown_template = resolver.select(["interface_shutdown"], ("interface",)) or resolver.select_bound(
                "interface",
                "enabled",
                direction="nb_to_cfg",
                required_params=("interface",),
            )
            no_shutdown_template = resolver.select(["interface_no_shutdown"], ("interface",)) or resolver.select_bound(
                "interface",
                "enabled",
                direction="nb_to_cfg",
                required_params=("interface",),
            )
            if interface.enabled and no_shutdown_template:
                operations.append(cls._build_operation(no_shutdown_template, {"interface": iface}))
            elif not interface.enabled and shutdown_template:
                operations.append(cls._build_operation(shutdown_template, {"interface": iface}))

            if interface.mode == InterfaceModeChoices.MODE_ACCESS:
                vlan_id = interface.untagged_vlan.vid if interface.untagged_vlan else None
                access_vlan_template = resolver.select_bound(
                    "interface",
                    "access_vlan",
                    direction="nb_to_cfg",
                    required_params=("interface",),
                ) or resolver.select(["access_vlan", "switchport_access_vlan"], ("interface",))
                if vlan_id and access_vlan_template:
                    param = "vlan_id" if "vlan_id" in access_vlan_template.params else "vlan"
                    operations.append(
                        cls._build_operation(
                            access_vlan_template,
                            {"interface": iface, param: str(vlan_id)},
                        )
                    )
                elif resolver.has(["switchport_mode_access"], ("interface",)):
                    template = resolver.select_bound(
                        "interface",
                        "mode",
                        direction="nb_to_cfg",
                        required_params=("interface",),
                    ) or resolver.select(["switchport_mode_access"], ("interface",))
                    operations.append(cls._build_operation(template, {"interface": iface}))

            if interface.mode in {InterfaceModeChoices.MODE_TAGGED, InterfaceModeChoices.MODE_TAGGED_ALL}:
                mode_template = resolver.select_bound(
                    "interface",
                    "mode",
                    direction="nb_to_cfg",
                    required_params=("interface",),
                ) or resolver.select(["switchport_mode_trunk"], ("interface",))
                if mode_template:
                    operations.append(cls._build_operation(mode_template, {"interface": iface}))

                if interface.untagged_vlan:
                    native_template = resolver.select_bound(
                        "interface",
                        "native_vlan",
                        direction="nb_to_cfg",
                        required_params=("interface", "vlan_id"),
                    ) or resolver.select(["switchport_trunk_native_vlan"], ("interface", "vlan_id"))
                    if native_template:
                        operations.append(
                            cls._build_operation(
                                native_template,
                                {"interface": iface, "vlan_id": str(interface.untagged_vlan.vid)},
                            )
                        )

                allowed_template = resolver.select_bound(
                    "interface",
                    "tagged_vlans",
                    direction="nb_to_cfg",
                    required_params=("interface",),
                ) or resolver.select(["switchport_trunk_allowed_vlan", "trunk_vlan"], ("interface",))
                if allowed_template:
                    if interface.mode == InterfaceModeChoices.MODE_TAGGED_ALL:
                        vlan_value = "all"
                    else:
                        vids = sorted(interface.tagged_vlans.values_list("vid", flat=True))
                        vlan_value = ",".join(str(vid) for vid in vids)
                    if vlan_value:
                        key = "vlan_list" if "vlan_list" in allowed_template.params else "vlan_id"
                        operations.append(
                            cls._build_operation(
                                allowed_template,
                                {"interface": iface, key: vlan_value},
                            )
                        )

            mtu_template = resolver.select_bound(
                "interface",
                "mtu",
                direction="nb_to_cfg",
                required_params=("interface", "mtu"),
            ) or resolver.select(["interface_mtu", "mtu"], ("interface", "mtu"))
            if mtu_template and interface.mtu:
                operations.append(
                    cls._build_operation(mtu_template, {"interface": iface, "mtu": str(interface.mtu)})
                )

            speed_template = resolver.select_bound(
                "interface",
                "speed",
                direction="nb_to_cfg",
                required_params=("interface", "speed"),
            ) or resolver.select(["speed", "interface_speed"], ("interface", "speed"))
            speed_cli = cls._speed_to_cli(interface.speed)
            if speed_template and speed_cli:
                operations.append(
                    cls._build_operation(speed_template, {"interface": iface, "speed": speed_cli})
                )

            duplex_template = resolver.select_bound(
                "interface",
                "duplex",
                direction="nb_to_cfg",
                required_params=("interface", "duplex"),
            ) or resolver.select(["duplex", "interface_duplex"], ("interface", "duplex"))
            if duplex_template and interface.duplex:
                operations.append(
                    cls._build_operation(duplex_template, {"interface": iface, "duplex": interface.duplex})
                )

            poe_mode_template = resolver.select_bound(
                "interface",
                "poe_mode",
                direction="nb_to_cfg",
                required_params=("interface",),
            ) or resolver.select(["interface_poe_mode", "poe_mode"], ("interface",))
            if poe_mode_template and interface.poe_mode:
                key = "poe_mode" if "poe_mode" in poe_mode_template.params else "mode"
                operations.append(
                    cls._build_operation(poe_mode_template, {"interface": iface, key: interface.poe_mode})
                )

            poe_type_template = resolver.select_bound(
                "interface",
                "poe_type",
                direction="nb_to_cfg",
                required_params=("interface",),
            ) or resolver.select(["interface_poe_type", "poe_type"], ("interface",))
            if poe_type_template and interface.poe_type:
                key = "poe_type" if "poe_type" in poe_type_template.params else "type"
                operations.append(
                    cls._build_operation(poe_type_template, {"interface": iface, key: interface.poe_type})
                )

        return operations

    @classmethod
    def _payload_for_netbox_state(cls, device: Device, profile: DevicePlatformProfile) -> dict[str, Any]:
        operations = cls._render_netbox_operations(device, profile)
        return {
            "schema_version": ConfigurationYamlService.SCHEMA_VERSION,
            "device": {"id": device.pk, "name": device.name},
            "platform": profile.platform,
            "source": "netbox",
            "operations": operations,
            "sections": [],
            "raw_commands": [],
        }

    @classmethod
    def _collect_operations_from_backup(cls, backup: ConfigurationBackup) -> list[dict[str, Any]]:
        if not ConfigurationYamlService.is_yaml_config(backup.config_text):
            return []
        payload = ConfigurationYamlService.load_payload(backup.config_text)
        operations = list(payload.get("operations") or [])
        for section in payload.get("sections") or []:
            operations.extend(section.get("operations") or [])
        return [item for item in operations if isinstance(item, dict)]

    @classmethod
    def _parse_config_intent(
        cls,
        operations: list[dict[str, Any]],
        resolver: _TemplateResolver | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        device_state: dict[str, Any] = {}
        interface_state: dict[str, dict[str, Any]] = {}

        def get_iface_state(name: str) -> dict[str, Any]:
            key = _normalize_interface_name(name)
            current = interface_state.get(key)
            if current is None:
                current = {"interface_name": name}
                interface_state[key] = current
            return current

        for operation in operations:
            name = str(operation.get("name", "")).strip().lower()
            operation_type = str(operation.get("operation_type", "")).strip().lower()
            params = operation.get("params") or {}
            if not isinstance(params, dict):
                continue

            iface = params.get("interface")
            state = get_iface_state(str(iface)) if iface else None
            semantic = resolver.semantics_for_operation(name, operation_type) if resolver else None

            if semantic == ("device", "hostname") and params.get("hostname"):
                device_state["hostname"] = str(params["hostname"]).strip()
                continue
            if name == "hostname" and params.get("hostname"):
                device_state["hostname"] = str(params["hostname"]).strip()
                continue

            if state is None:
                continue

            if semantic == ("interface", "enabled"):
                if "no" in name and "shutdown" in name:
                    state["enabled"] = True
                elif "shutdown" in name:
                    state["enabled"] = False
            if semantic == ("interface", "description") and params.get("description") is not None:
                state["description"] = str(params.get("description", ""))
            if semantic == ("interface", "mtu") and params.get("mtu") is not None:
                state["mtu"] = _parse_int(params.get("mtu"))
            if semantic == ("interface", "speed") and params.get("speed") is not None:
                state["speed"] = cls._speed_to_netbox(params.get("speed"))
            if semantic == ("interface", "duplex") and params.get("duplex") is not None:
                state["duplex"] = str(params.get("duplex")).strip().lower()
            if semantic == ("interface", "poe_mode"):
                raw_mode = params.get("poe_mode", params.get("mode"))
                if raw_mode is not None:
                    state["poe_mode"] = str(raw_mode).strip().lower()
            if semantic == ("interface", "poe_type"):
                raw_type = params.get("poe_type", params.get("type"))
                if raw_type is not None:
                    state["poe_type"] = str(raw_type).strip().lower()
            if semantic == ("interface", "mode"):
                if "access" in name:
                    state["mode"] = "access"
                elif "trunk" in name:
                    state["mode"] = "trunk"
            if semantic == ("interface", "access_vlan"):
                raw_vlan = params.get("vlan_id", params.get("vlan"))
                state["access_vlan"] = _parse_int(raw_vlan)
                state["mode"] = "access"
            if semantic == ("interface", "native_vlan"):
                raw_native = params.get("vlan_id", params.get("vlan"))
                state["native_vlan"] = _parse_int(raw_native)
                state["mode"] = "trunk"
            if semantic == ("interface", "tagged_vlans"):
                value = params.get("vlan_list", params.get("vlan_id", params.get("vlans")))
                state["trunk_allowed"] = value
                state["mode"] = "trunk-all" if str(value).strip().lower() == "all" else "trunk"

            if name == "interface_shutdown" or ("shutdown" in name and "no_shutdown" not in name):
                state["enabled"] = False
            if name == "interface_no_shutdown" or "no_shutdown" in name:
                state["enabled"] = True
            if "description" in name and params.get("description") is not None:
                state["description"] = str(params.get("description", ""))
            if ("mtu" in name) and params.get("mtu") is not None:
                state["mtu"] = _parse_int(params.get("mtu"))
            if ("speed" in name) and params.get("speed") is not None:
                state["speed"] = cls._speed_to_netbox(params.get("speed"))
            if ("duplex" in name) and params.get("duplex") is not None:
                state["duplex"] = str(params.get("duplex")).strip().lower()
            if ("poe" in name) and params.get("poe_mode") is not None:
                state["poe_mode"] = str(params.get("poe_mode")).strip().lower()
            if ("poe" in name) and params.get("poe_type") is not None:
                state["poe_type"] = str(params.get("poe_type")).strip().lower()
            if name in {"switchport_mode_access", "access_vlan", "switchport_access_vlan"}:
                state["mode"] = "access"
            if name in {"switchport_mode_trunk", "trunk_vlan", "switchport_trunk_allowed_vlan"}:
                state["mode"] = "trunk"
            if params.get("vlan_id") is not None and name in {"access_vlan", "switchport_access_vlan"}:
                state["access_vlan"] = _parse_int(params.get("vlan_id"))
            if params.get("vlan") is not None and name in {"access_vlan", "switchport_access_vlan"}:
                state["access_vlan"] = _parse_int(params.get("vlan"))
            if name in {"trunk_vlan", "switchport_trunk_allowed_vlan"}:
                value = params.get("vlan_list", params.get("vlan_id", params.get("vlans")))
                state["trunk_allowed"] = value
                if str(value).strip().lower() == "all":
                    state["mode"] = "trunk-all"
            if name == "switchport_trunk_native_vlan":
                state["native_vlan"] = _parse_int(params.get("vlan_id"))

        return device_state, interface_state

    @classmethod
    def _candidate_vlans(cls, device: Device) -> list[VLAN]:
        return list(VLAN.objects.filter(site__in=[device.site, None]).order_by("vid", "pk"))

    @classmethod
    def _apply_device_state(cls, device: Device, state: dict[str, Any], changed_fields: list[str]) -> None:
        hostname = state.get("hostname")
        if not hostname or hostname == device.name:
            return
        if Device.objects.exclude(pk=device.pk).filter(name=hostname).exists():
            logger.warning(
                "Skipping hostname sync because device name already exists %s new_name=%s",
                device_log_context(device),
                hostname,
            )
            return
        device.name = hostname
        device.save(update_fields=("name", "last_updated"))
        changed_fields.append("device.name")

    @classmethod
    def _apply_interface_state(
        cls,
        device: Device,
        state_map: dict[str, dict[str, Any]],
        changed_fields: list[str],
    ) -> None:
        if not state_map:
            return

        interfaces = cls._interfaces_for_device(device)
        index: dict[str, Interface] = {}
        for item in interfaces:
            index[_normalize_interface_name(item.name)] = item

        vlan_by_vid: dict[int, VLAN] = {}
        for vlan in cls._candidate_vlans(device):
            vlan_by_vid.setdefault(vlan.vid, vlan)

        for normalized_name, desired in state_map.items():
            interface = index.get(normalized_name)
            if not interface:
                continue
            dirty_fields: set[str] = set()
            tagged_target: set[int] | None = None

            if "description" in desired and interface.description != desired["description"]:
                interface.description = desired["description"]
                dirty_fields.add("description")

            if "enabled" in desired and interface.enabled != bool(desired["enabled"]):
                interface.enabled = bool(desired["enabled"])
                dirty_fields.add("enabled")

            if "mtu" in desired and desired["mtu"] and interface.mtu != desired["mtu"]:
                interface.mtu = desired["mtu"]
                dirty_fields.add("mtu")

            if "speed" in desired and desired["speed"] and interface.speed != desired["speed"]:
                interface.speed = desired["speed"]
                dirty_fields.add("speed")

            if "duplex" in desired:
                value = str(desired["duplex"]).lower()
                if value in {InterfaceDuplexChoices.DUPLEX_HALF, InterfaceDuplexChoices.DUPLEX_FULL, InterfaceDuplexChoices.DUPLEX_AUTO}:
                    if interface.duplex != value:
                        interface.duplex = value
                        dirty_fields.add("duplex")

            if "poe_mode" in desired:
                value = str(desired["poe_mode"]).lower()
                if value in {InterfacePoEModeChoices.MODE_PD, InterfacePoEModeChoices.MODE_PSE}:
                    if interface.poe_mode != value:
                        interface.poe_mode = value
                        dirty_fields.add("poe_mode")

            if "poe_type" in desired:
                value = str(desired["poe_type"]).lower()
                valid_types = {
                    InterfacePoETypeChoices.TYPE_1_8023AF,
                    InterfacePoETypeChoices.TYPE_2_8023AT,
                    InterfacePoETypeChoices.TYPE_3_8023BT,
                    InterfacePoETypeChoices.TYPE_4_8023BT,
                    InterfacePoETypeChoices.PASSIVE_24V_2PAIR,
                    InterfacePoETypeChoices.PASSIVE_24V_4PAIR,
                    InterfacePoETypeChoices.PASSIVE_48V_2PAIR,
                    InterfacePoETypeChoices.PASSIVE_48V_4PAIR,
                }
                if value in valid_types and interface.poe_type != value:
                    interface.poe_type = value
                    dirty_fields.add("poe_type")

            mode = desired.get("mode")
            if mode == "access":
                if interface.mode != InterfaceModeChoices.MODE_ACCESS:
                    interface.mode = InterfaceModeChoices.MODE_ACCESS
                    dirty_fields.add("mode")
                vlan_id = desired.get("access_vlan")
                new_vlan = vlan_by_vid.get(vlan_id) if vlan_id else None
                if interface.untagged_vlan_id != getattr(new_vlan, "pk", None):
                    interface.untagged_vlan = new_vlan
                    dirty_fields.add("untagged_vlan")
            elif mode == "trunk":
                if interface.mode != InterfaceModeChoices.MODE_TAGGED:
                    interface.mode = InterfaceModeChoices.MODE_TAGGED
                    dirty_fields.add("mode")
                native = desired.get("native_vlan")
                new_native = vlan_by_vid.get(native) if native else interface.untagged_vlan
                if native is not None and interface.untagged_vlan_id != getattr(new_native, "pk", None):
                    interface.untagged_vlan = new_native
                    dirty_fields.add("untagged_vlan")
                if desired.get("trunk_allowed") is not None:
                    tagged_target = _parse_vlan_set(desired.get("trunk_allowed"))
            elif mode == "trunk-all":
                if interface.mode != InterfaceModeChoices.MODE_TAGGED_ALL:
                    interface.mode = InterfaceModeChoices.MODE_TAGGED_ALL
                    dirty_fields.add("mode")

            if dirty_fields:
                interface.save(update_fields=tuple(sorted(dirty_fields)) + ("last_updated",))
                for field in sorted(dirty_fields):
                    changed_fields.append(f"interface:{interface.name}:{field}")

            if tagged_target is not None and interface.mode == InterfaceModeChoices.MODE_TAGGED:
                tagged_objects = [vlan for vid, vlan in vlan_by_vid.items() if vid in tagged_target]
                current = set(interface.tagged_vlans.values_list("vid", flat=True))
                desired_vids = {vlan.vid for vlan in tagged_objects}
                if current != desired_vids:
                    interface.tagged_vlans.set(tagged_objects)
                    changed_fields.append(f"interface:{interface.name}:tagged_vlans")

    @classmethod
    def sync_from_configuration_backup(
        cls,
        backup: ConfigurationBackup,
        *,
        origin: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation = correlation_id or uuid.uuid4().hex
        device = backup.device

        if not cls.should_sync_from_config():
            cls._log(
                device=device,
                direction=cls.DIRECTION_CONFIG_TO_NETBOX,
                status=cls.STATUS_SKIPPED,
                origin=origin,
                message="Config to NetBox sync is disabled.",
                backup=backup,
                correlation_id=correlation,
            )
            return {"status": "skipped", "reason": "disabled"}

        operations = cls._collect_operations_from_backup(backup)
        if not operations:
            cls._log(
                device=device,
                direction=cls.DIRECTION_CONFIG_TO_NETBOX,
                status=cls.STATUS_SKIPPED,
                origin=origin,
                message="No parsed operations in backup.",
                backup=backup,
                correlation_id=correlation,
            )
            return {"status": "skipped", "reason": "no_operations"}

        changed_fields: list[str] = []
        try:
            profile = DevicePlatformProfile.objects.filter(device=device, enabled=True).first()
            resolver = _TemplateResolver(profile) if profile else None
            device_state, interface_state = cls._parse_config_intent(operations, resolver=resolver)
            with suppress_netbox_sync():
                cls._apply_device_state(device, device_state, changed_fields)
                cls._apply_interface_state(device, interface_state, changed_fields)
            cls._log(
                device=device,
                direction=cls.DIRECTION_CONFIG_TO_NETBOX,
                status=cls.STATUS_SUCCESS,
                origin=origin,
                message="Config parameters applied to NetBox objects.",
                changed_fields=changed_fields,
                backup=backup,
                correlation_id=correlation,
            )
            return {"status": "success", "changed_fields": changed_fields}
        except Exception as exc:
            logger.exception(
                "Config to NetBox sync failed %s backup_id=%s correlation_id=%s error=%s",
                device_log_context(device),
                backup.pk,
                correlation,
                exc,
            )
            cls._log(
                device=device,
                direction=cls.DIRECTION_CONFIG_TO_NETBOX,
                status=cls.STATUS_FAILED,
                origin=origin,
                message=str(exc),
                changed_fields=changed_fields,
                backup=backup,
                correlation_id=correlation,
            )
            raise

    @classmethod
    def sync_from_netbox_device(
        cls,
        device: Device,
        *,
        origin: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation = correlation_id or uuid.uuid4().hex

        if not cls.should_sync_on_netbox_change():
            cls._log(
                device=device,
                direction=cls.DIRECTION_NETBOX_TO_CONFIG,
                status=cls.STATUS_SKIPPED,
                origin=origin,
                message="NetBox to config sync is disabled.",
                correlation_id=correlation,
            )
            return {"status": "skipped", "reason": "disabled"}

        if is_netbox_sync_suppressed():
            return {"status": "skipped", "reason": "suppressed"}

        debounce_key = f"cw:sync:debounce:{device.pk}"
        if not cache.add(debounce_key, "1", timeout=cls.debounce_seconds()):
            return {"status": "skipped", "reason": "debounced"}

        profile = DevicePlatformProfile.objects.filter(device=device, enabled=True).first()
        if not profile:
            cls._log(
                device=device,
                direction=cls.DIRECTION_NETBOX_TO_CONFIG,
                status=cls.STATUS_SKIPPED,
                origin=origin,
                message="No active device profile.",
                correlation_id=correlation,
            )
            return {"status": "skipped", "reason": "no_profile"}

        try:
            payload = cls._payload_for_netbox_state(device, profile)
            yaml_text = ConfigurationYamlService.dump_yaml(payload)
            TaskExecutor.apply_yaml_to_device(device, yaml_text)
            latest = ConfigurationRepository.latest_backup_for_device(device.pk)
            if latest:
                from .gitlab import GitLabIntegrationService

                GitLabIntegrationService.push_backup_to_gitlab(latest, source=GitLabIntegrationService.SOURCE_PLUGIN)

            cls._log(
                device=device,
                direction=cls.DIRECTION_NETBOX_TO_CONFIG,
                status=cls.STATUS_SUCCESS,
                origin=origin,
                message="NetBox parameters applied to device and pushed to GitLab.",
                correlation_id=correlation,
            )
            return {"status": "success", "backup_id": getattr(latest, "pk", None)}
        except Exception as exc:
            logger.exception(
                "NetBox to config sync failed %s correlation_id=%s error=%s",
                device_log_context(device, profile),
                correlation,
                exc,
            )
            cls._log(
                device=device,
                direction=cls.DIRECTION_NETBOX_TO_CONFIG,
                status=cls.STATUS_FAILED,
                origin=origin,
                message=str(exc),
                correlation_id=correlation,
            )
            raise
