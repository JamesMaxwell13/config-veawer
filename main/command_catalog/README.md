# Command Catalog

This directory contains built-in command templates for config-weaver.

- `cisco.yaml` - Cisco IOS-style templates.
- `dlink.yaml` - D-Link templates.

The catalog is not intended to be a complete vendor CLI reference. It is a reusable baseline for common operations and for converting saved running-config YAML back into commands.

The files are packaged with the plugin through `MANIFEST.in`. After changing them, reinstalling the editable package is usually not required, but the database copy must be synchronized with `sync_command_templates`.

## Template Sources

At runtime config-weaver merges two sources:

1. Built-in YAML templates from this directory.
2. Active `CommandTemplate` objects stored in NetBox.

If a database template has the same `vendor`, `platform`, `operation_type`, and `name` as a built-in template, the database template wins. This lets an operator override built-in behavior without editing plugin files.

The plugin caches active templates under the `cw:templates:active` cache key. Saving or deleting a `CommandTemplate`, or running `sync_command_templates`, invalidates that cache.

Run template sync from the NetBox app directory:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py sync_command_templates
```

Dry run:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py sync_command_templates --dry-run
```

## YAML Template Format

Each vendor file starts with `vendor` and `templates`:

```yaml
vendor: cisco
templates:
  - name: interface_l3
    platform: cisco_ios
    operation_type: ip
    revision: 1
    description: Configure routed interface IPv4 address.
    params: [interface, ip, mask]
    command_body: |
      interface {interface}
      no switchport
      ip address {ip} {mask}
      no shutdown
```

Required fields:

- `name` - stable operation name used in YAML plans and parsed backups.
- `platform` - platform from `DevicePlatformProfile`, for example `cisco_ios` or `dlink_ds`.
- `operation_type` - operation group accepted by the `CommandTemplate` model: `interface`, `vlan`, `ip`, or `custom`.
- `command_body` - one or more CLI commands.

Recommended fields:

- `revision` - increase when the template behavior changes.
- `description` - short purpose statement.
- `params` - placeholder names used by `command_body`.

Placeholders use Python `str.format` style:

```yaml
command_body: |
  interface {interface}
  description {description}
```

Input operation:

```yaml
operations:
  - name: interface_description
    params:
      interface: GigabitEthernet0/1
      description: uplink-to-core
```

If a required placeholder is missing, preview and execution fail before commands are sent to the device.

Keep template names stable. Existing backups, `NetworkTask.plan_yaml`, GitLab desired-state files, and scheduled task YAML can all refer to these names.

## Running-Config YAML And Sections

Raw running-config backups are converted into config-weaver YAML.

Schema v2 preserves contextual sections:

- `interface ...`
- `line ...`
- `router ...`
- `ip access-list ...`
- `ipv6 access-list ...`
- `gatekeeper`
- `control-plane`
- other recognized Cisco blocks.

This means child commands such as `shutdown`, `login`, `duplex half`, ACL entries, tunnel commands, and line settings remain attached to their parent section.

Top-level `raw_commands` should contain only unmatched global commands. Section-specific unmatched commands belong in that section's `raw_commands`.

## Cisco Coverage

The Cisco catalog currently covers the main command families used by the tested running-config samples:

- global hostname, password, service, CEF, IPv6, HTTP, CDP, and flow-export commands;
- spanning-tree mode and VLAN priority;
- interface IP, no IP address, NAT inside/outside, shutdown/no shutdown, duplex, speed;
- switchport trunk native/allowed VLANs, encapsulation, trunk mode;
- Port-channel membership with `channel-group`;
- SVI MAC address, IPv4 address, and inbound ACL binding;
- IPv6 address, IPv6 enable, tunnel source/mode/destination, IPv6 routes;
- standard and extended named ACL entries;
- static IPv4 routes and static NAT;
- RIP router section;
- console/aux/vty line password, login, transport, timeout, privilege, logging, and stopbits.

Rare commands that do not need reuse can stay as `raw_commands`.

Supported Cisco-family platform identifiers are `cisco_ios`, `cisco_xe`, and `cisco_nxos`; the current built-in catalog mainly targets `cisco_ios`. Supported D-Link-family identifiers are `dlink_ds` and `dlink_dgs`; the current built-in D-Link catalog mainly targets `dlink_ds`.

## Adding A Cisco Template

Add a new item to `cisco.yaml`:

```yaml
  - name: ospf_network
    platform: cisco_ios
    operation_type: ip
    revision: 1
    description: Add an OSPF network statement.
    params: [process_id, network, wildcard, area]
    command_body: |
      router ospf {process_id}
      network {network} {wildcard} area {area}
```

Use it in a task or backup YAML:

```yaml
operations:
  - name: ospf_network
    params:
      process_id: 1
      network: 10.0.0.0
      wildcard: 0.0.0.255
      area: 0
```

Rendered commands:

```text
router ospf 1
network 10.0.0.0 0.0.0.255 area 0
```

## Adding A D-Link Template

Add a new item to `dlink.yaml`:

```yaml
  - name: access_vlan_named
    platform: dlink_ds
    operation_type: vlan
    revision: 1
    description: Create VLAN and assign an untagged access port.
    params: [vlan_id, vlan_name, interface]
    command_body: |
      create vlan {vlan_name} tag {vlan_id}
      config vlan {vlan_name} add untagged {interface}
```

Then reference `access_vlan_named` from `NetworkTask.plan_yaml` or a rendered configuration YAML.

## Validation Checklist

After editing templates:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py sync_command_templates --dry-run
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main.tests.test_command_catalog --keepdb
```

For parser/template interactions, also run the focused configuration refresh tests:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main.tests.test_config_refresh --keepdb
```

If the change affects scheduled execution, GitLab import/export, or command rendering from UI forms, also run the matching focused tests:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main.tests.test_scheduling --keepdb
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main.tests.test_gitlab_integration --keepdb
```
