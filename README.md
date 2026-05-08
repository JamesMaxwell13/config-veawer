# config-weaver

`config-weaver` - NetBox 4.x plugin for network device configuration management.

The plugin adds device connection profiles, encrypted credentials, command templates, scheduled tasks, configuration backups, YAML-based configuration rendering, a manual WebSocket terminal, Git-backed version storage, and a plugin-local Swagger UI.

## Repository Layout

The local diploma workspace is expected to look like this:

```text
/home/andrew/bsuir/diploma/
├── config-weaver/      # plugin source
├── config-weaver-vcs/  # optional Git repository for configuration versions
└── netbox/             # NetBox source tree and virtualenv
```

Run NetBox management commands from:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
```

Run plugin-local commands from:

```bash
cd /home/andrew/bsuir/diploma/config-weaver
```

## Requirements

- NetBox 4.x, tested with the local NetBox 4.5.x tree.
- Python virtualenv at `/home/andrew/bsuir/diploma/netbox/venv`.
- PostgreSQL configured for NetBox.
- Redis configured for NetBox tasks and caching.
- Python packages used by the plugin: `pyyaml`, `netmiko`, `paramiko`, `cryptography`, `channels`, `daphne`.
- Git available on the host if configuration version files should be committed.

## Installation

Install runtime dependencies into the NetBox virtualenv:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install \
  pyyaml netmiko paramiko cryptography channels daphne
```

Install the plugin in editable mode:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install -e \
  /home/andrew/bsuir/diploma/config-weaver
```

Check that the package is visible:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip show netbox-config-weaver
```

## NetBox Configuration

Add the plugin to NetBox `configuration.py`.

The plugin module name is `main`; the public UI/API base URL is `config-weaver`.

```python
PLUGINS = ["main"]

PLUGINS_CONFIG = {
    "main": {
        "secret_key": "replace-with-a-long-random-plugin-secret",
        "vcs_repo_path": "/home/andrew/bsuir/diploma/config-weaver-vcs",
        "scheduler_max_workers": 8,
    }
}
```

The full example is in `examples/netbox_plugin_configuration.py`.

`secret_key` is required and is used to encrypt stored device credential secrets. Keep it stable after first use; changing it will make previously encrypted credential values unreadable.

`vcs_repo_path` is optional. If omitted, the plugin falls back to `MEDIA_ROOT/config_weaver_repo`.

`scheduler_max_workers` is optional. Invalid values fall back to `8`; values below `1` are treated as `1`.

## Database And Initial Data

Run migrations:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py migrate
```

Sync built-in command templates into the database:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py sync_command_templates
```

Preview template sync without writing:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py sync_command_templates --dry-run
```

Run a basic Django check:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py check
```

## Local Run

Use the workspace `Makefile` from `/home/andrew/bsuir/diploma`.

Run NetBox ASGI, RQ worker, and the config-weaver scheduler loop:

```bash
cd /home/andrew/bsuir/diploma
make run
```

Run only the ASGI web process:

```bash
make run-web
```

Run only the RQ worker:

```bash
make run-worker
```

Run only the config-weaver scheduled task loop:

```bash
make run-scheduler
```

The manual device terminal requires ASGI/Daphne. Do not use `manage.py runserver` for terminal testing; it serves WSGI/HTTP only and does not handle `/ws/plugins/config-weaver/...`.

## UI

After startup, the plugin appears in the NetBox menu as `Config Weaver`.

Main pages:

- `/plugins/config-weaver/devices/` - device connection profiles.
- `/plugins/config-weaver/credentials/` - encrypted SSH credentials.
- `/plugins/config-weaver/configurations/` - saved configuration backups.
- `/plugins/config-weaver/tasks/` - scheduled tasks.
- `/plugins/config-weaver/templates/` - command templates.
- `/plugins/config-weaver/uml/` - UML configuration render objects.
- `/plugins/config-weaver/api/docs/` - Swagger UI for plugin REST API.

List pages support NetBox-style bulk edit and bulk delete actions where applicable.

## REST API And Swagger

REST API base URL:

```text
/api/plugins/config-weaver/
```

Swagger UI:

```text
/plugins/config-weaver/api/docs/
```

OpenAPI schema:

```text
/plugins/config-weaver/api/schema/
```

Examples:

```bash
curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/config-weaver/devices/

curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/config-weaver/configurations/by_device/?device_id=1

curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/config-weaver/configurations/compare/?from=1\&to=2
```

The old `/api/plugins/main/...` examples are obsolete. NetBox registers the plugin under the public `base_url = "config-weaver"`.

## Configuration Workflow

1. Create a `DeviceCredential`.
2. Create a `DevicePlatformProfile` for a NetBox `dcim.Device`.
3. Click `Получить конфигурацию` from the profile or device configuration tab.
4. The plugin connects to the device, reads running-config, stores a new `ConfigurationBackup` if the content changed, and redirects to `/plugins/config-weaver/configurations/<id>/`.
5. The configuration page shows the rendered YAML and available actions.

If the running-config did not change, the plugin redirects to the existing current backup.

Configuration refresh uses the device profile and credential. The test virtual environment can use normal SSH credentials such as `admin/admin`, but production values should be stored only through `DeviceCredential`.

## YAML Configuration Format

Raw running-config is converted into plugin YAML.

Current YAML schema version is `2`. Schema v1 remains readable for older saved backups.

Schema v2 separates:

- `operations` - matched global commands rendered through command templates.
- `sections` - contextual blocks such as `interface`, `line`, `router`, `ip access-list`, `gatekeeper`, and similar Cisco sections.
- `raw_commands` - unmatched top-level global commands only.

This prevents commands like `shutdown`, `login`, `duplex half`, ACL rules, or tunnel commands from losing their parent section.

Example shape:

```yaml
schema_version: 2
device:
  name: Switch3
operations:
  - name: hostname
    params:
      hostname: Switch3
sections:
  - header: interface FastEthernet0/5
    operations:
      - name: shutdown
        params: {}
    raw_commands: []
raw_commands: []
```

Restoring a YAML backup renders known operations through templates and sends raw commands in their preserved context.

## Command Templates

Built-in templates live in `main/command_catalog/`.

Sources are merged in this order:

1. Built-in YAML templates from `cisco.yaml` and `dlink.yaml`.
2. Active `CommandTemplate` objects from the NetBox database.

Database templates with the same `vendor`, `platform`, `operation_type`, and `name` override built-in templates.

The Cisco catalog covers common commands from the tested running-config samples, including trunk ports, channel groups, SVI IP addresses, ACLs, IPv6 tunnel/routing, NAT, line configuration, spanning tree, and basic service/global commands.

Use `raw_commands` only for rare commands that do not need reusable parameterized templates.

## Manual Device Terminal

Terminal URL:

```text
/plugins/config-weaver/devices/<profile_id>/terminal/
```

WebSocket URL:

```text
/ws/plugins/config-weaver/devices/<profile_id>/terminal/
```

The terminal supports command history with Arrow Up and Arrow Down.

Unauthenticated WebSocket diagnostic request should return `403 Access denied`, which means ASGI routing is working but the request has no NetBox session.

If it returns `404 Not Found` from `WSGIServer`, NetBox was started through WSGI `runserver`; use `make run` or `make run-web`.

Diagnostic command:

```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  http://127.0.0.1:8000/ws/plugins/config-weaver/devices/1/terminal/
```

## Scheduler

Scheduled tasks are executed by `run_due_tasks`.

Local development can run the scheduler through:

```bash
cd /home/andrew/bsuir/diploma
make run-scheduler
```

Production can run it through cron, systemd timer, or a dedicated service loop.

Example cron entry:

```cron
* * * * * cd /home/andrew/bsuir/diploma/netbox/netbox && /home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py run_due_tasks >> /tmp/config-weaver.log 2>&1
```

RQ worker is still required for NetBox background work:

```bash
cd /home/andrew/bsuir/diploma
make run-worker
```

## Git Version Repository

Configuration versions are stored in the database and mirrored into a Git repository as JSON files when VCS storage is enabled.

Default local path:

```text
/home/andrew/bsuir/diploma/config-weaver-vcs
```

Prepare it manually if you want explicit permissions:

```bash
mkdir -p /home/andrew/bsuir/diploma/config-weaver-vcs
chmod 755 /home/andrew/bsuir/diploma/config-weaver-vcs
```

Commit messages use:

```text
backup(<device_name>): version <N>
```

## Production Notes

- Do not edit NetBox core files for this plugin.
- Serve HTTP through the usual NetBox backend.
- Serve terminal WebSocket traffic through ASGI with `/ws/` upgrade headers.
- Serve static files from `STATIC_ROOT` through nginx or another HTTP server.
- Run a NetBox RQ worker.
- Run `run_due_tasks` through a scheduler.

Required nginx headers for `/ws/`:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```

## Troubleshooting

Plugin is not visible:

1. Check `PLUGINS = ["main"]`.
2. Check `python -m pip show netbox-config-weaver`.
3. Run `python manage.py migrate`.
4. Restart NetBox.

Cannot connect to a device:

- `Connection refused`: check `management_ip`, `ssh_port`, firewall, and SSH service.
- `Authentication failed`: check `DeviceCredential`.
- `Timeout`: check reachability and credential/profile timeout.
- No saved configuration after command execution: verify that the device accepts `show running-config` and save commands for its platform.

Terminal does not connect:

1. Use `make run` or `make run-web`, not `manage.py runserver`.
2. Check that `/ws/plugins/config-weaver/devices/<id>/terminal/` does not return `404`.
3. Check NetBox login session and `change_deviceplatformprofile` permission.
4. Check reverse proxy WebSocket headers.

Swagger does not load:

1. Open `/plugins/config-weaver/api/docs/` while logged into NetBox.
2. Check `/plugins/config-weaver/api/schema/?format=json`.
3. Run `python manage.py check`.

YAML restore fails:

1. Validate YAML syntax.
2. Check that `schema_version` is supported.
3. Check that operation names exist in built-in templates or active `CommandTemplate` objects.
4. Keep truly unsupported commands under contextual `raw_commands`.

## Development Checks

Common focused checks:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py check
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main.tests.test_swagger --keepdb
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main.tests.test_config_refresh --keepdb
```

Known note: older UI assertion tests may need updates when YAML/diff rendering markup changes, even if the application behavior is correct.
