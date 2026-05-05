## config-weaver

Django/NetBox plugin for automated network configuration management.

### Установка и запуск с NetBox

Раздел описывает локальный запуск проекта из текущей структуры:

```text
/home/andrew/bsuir/diploma/
├── config-weaver/      # код плагина
└── netbox/             # исходники NetBox и virtualenv
```

#### 1. Требования

- Python 3.12+
- PostgreSQL
- Redis
- Git
- NetBox 4.5.x или совместимый NetBox 4.x

Проверка локальных сервисов:

```bash
redis-cli ping
```

Ожидаемый ответ Redis:

```text
PONG
```

PostgreSQL должен содержать базу и пользователя NetBox. Для локального стенда используется:

```text
database: netbox
user: netbox
password: NETBOX2026
host: localhost
port: 5432
```

Если база уже создана и права выданы, этот шаг повторять не нужно.

#### 2. Активировать окружение NetBox

```bash
cd /home/andrew/bsuir/diploma/netbox
source venv/bin/activate
```

В этом окружении `pip` может иметь битый wrapper после переноса директории. Надежный вариант установки пакетов:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install --upgrade pip
```

#### 3. Установить зависимости плагина

```bash
cd /home/andrew/bsuir/diploma/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install pyyaml netmiko paramiko cryptography channels daphne
```

#### 4. Установить плагин в editable-режиме

```bash
cd /home/andrew/bsuir/diploma/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install -e /home/andrew/bsuir/diploma/config-weaver
```

Проверка, что пакет установлен:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip show netbox-config-weaver
```

В выводе должен быть пакет `netbox-config-weaver`.

#### 5. Настроить NetBox

Открыть файл:

```text
/home/andrew/bsuir/diploma/netbox/netbox/netbox/configuration.py
```

Минимальная рабочая конфигурация для локального стенда:

```python
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'netbox',
        'USER': 'netbox',
        'PASSWORD': 'NETBOX2026',
        'HOST': 'localhost',
        'PORT': '5432',
        'CONN_MAX_AGE': 300,
    }
}

REDIS = {
    'tasks': {
        'HOST': 'localhost',
        'PORT': 6379,
        'USERNAME': '',
        'PASSWORD': '',
        'DATABASE': 0,
        'SSL': False,
    },
    'caching': {
        'HOST': 'localhost',
        'PORT': 6379,
        'USERNAME': '',
        'PASSWORD': '',
        'DATABASE': 1,
        'SSL': False,
    }
}

SECRET_KEY = 'replace-with-a-random-string-at-least-50-characters-long'

API_TOKEN_PEPPERS = {
    1: 'replace-with-a-random-string-at-least-50-characters-long',
}

PLUGINS = ['main']

PLUGINS_CONFIG = {
    'main': {
        'secret_key': 'config-weaver-local-development-secret',
        'vcs_repo_path': '/home/andrew/bsuir/diploma/config-weaver-vcs',
        'scheduler_max_workers': 8,
    }
}
```

Важно: `PLUGINS = ['main']` соответствует имени плагина в `main/__init__.py`.

Короткий пример только с настройками плагина лежит в `examples/netbox_plugin_configuration.py`.
Этот файл не загружается автоматически; значения из него нужно перенести в `configuration.py` NetBox.

#### 6. Проверить конфигурацию Django

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py check
```

Успешный результат:

```text
System check identified no issues (0 silenced).
```

#### 7. Примените миграции

Сначала можно проверить миграции плагина:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py showmigrations main
```

Затем применить все миграции NetBox и плагина:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py migrate
```

Если все уже применено, Django выведет:

```text
No migrations to apply.
```

#### 8. Собрать статические файлы

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py collectstatic --noinput
```

После этого файлы должны лежать в:

```text
/home/andrew/bsuir/diploma/netbox/netbox/static
```

#### 9. Создать администратора NetBox

Если суперпользователь еще не создан:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py createsuperuser
```

#### 10. Запустить NetBox с плагином

Чтобы запустить полный локальный стенд, нужно выполнить:

```bash
cd /home/andrew/bsuir/diploma
make run
```

Эта команда должна запустить три процесса:

- запустить NetBox через ASGI/Daphne на `HOST:PORT`;
- запустить NetBox RQ worker для очередей `high default low`;
- запустить цикл планировщика config-weaver, который выполняет `run_due_tasks` каждые `SCHEDULER_INTERVAL` секунд.

По умолчанию нужно открыть:

```text
http://127.0.0.1:8000/
```

Чтобы изменить адрес или порт, нужно передать переменные `make`:

```bash
make run HOST=127.0.0.1 PORT=8001
```

Чтобы запустить только web-процесс без worker и планировщика, нужно выполнить:

```bash
make run-web
```

Чтобы запустить только RQ worker, нужно выполнить:

```bash
make run-worker
```

Чтобы запустить только цикл планировщика config-weaver, нужно выполнить:

```bash
make run-scheduler
```

Чтобы один раз выполнить просроченные задачи без постоянного цикла, нужно выполнить:

```bash
make run-due-tasks
```

Чтобы проверить runtime-зависимости перед запуском, нужно выполнить:

```bash
make check-runtime
```

Эта проверка должна подтвердить доступность `daphne`, Redis и подключения Django к PostgreSQL.

Проверить ответ приложения нужно так:

```bash
curl -I http://127.0.0.1:8000/
```

Для закрытого NetBox нормальный ответ на главную страницу:

```text
HTTP/1.1 302 Found
Location: /login/?next=/
```

Проверить статику нужно так:

```bash
curl -I http://127.0.0.1:8000/static/netbox.css
curl -I http://127.0.0.1:8000/static/netbox.js
curl -I http://127.0.0.1:8000/static/setmode.js
```

Все три запроса должны возвращать `200 OK`.

#### 11. Учесть нюансы WebSocket-терминала

Чтобы пользоваться ручным терминалом устройства, нужно запускать NetBox через ASGI/Daphne, то есть через `make run` или `make run-web`. Обычный Django WSGI `runserver` не обрабатывает WebSocket-маршрут `/ws/plugins/config-weaver/devices/<pk>/terminal/`.

Чтобы сохранить NetBox без core-правок, нужно использовать ASGI entrypoint плагина и держать изменения внутри `config-weaver`. Подробности: [RAEDME_NETBOX_CHANGE.md](RAEDME_NETBOX_CHANGE.md).

Если открыть терминал при запуске через WSGI, браузер покажет ошибку WebSocket-соединения, а прямой запрос к `/ws/.../terminal/` обычно вернет `404 Not Found` от `WSGIServer`. Это означает, что запрос попал не в Channels consumer, а в обычный HTTP URL resolver.

Если WebSocket-маршрут обрабатывается Daphne, но пользователь не авторизован, тестовый handshake без cookie должен вернуть `403 Access denied`. Для локальной диагностики это нормальный признак: ASGI routing работает, но нет сессии NetBox.

Чтобы проверить WebSocket routing без браузера, можно выполнить:

```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  http://127.0.0.1:8000/ws/plugins/config-weaver/devices/1/terminal/
```

Ожидаемая диагностика:

- получить `403 Access denied` без cookie авторизованной сессии - ASGI/Daphne и route работают;
- получить `404 Not Found` от `WSGIServer` - нужно остановить WSGI `runserver` и запустить `make run`;
- получить ошибку `Connection refused` - нужно проверить, что `make run` слушает нужный порт;
- получить `400 bad Sec-WebSocket-Key` - нужно проверить корректность тестового заголовка `Sec-WebSocket-Key`.

Для HTTPS-прокси нужно прокидывать WebSocket upgrade-заголовки и использовать `wss://` на стороне браузера. Минимально нужно настроить:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```

Статика при локальном Daphne обслуживается через `ASGIStaticFilesHandler` в `main.asgi:application`. В production нужно раздавать `STATIC_ROOT` через nginx или другой HTTP-сервер.

#### 12. Проверить плагин в интерфейсе

1. Открыть `http://127.0.0.1:8000/`.
2. Войти под суперпользователем.
3. Проверить, что в меню появился раздел `config-weaver`.
4. Проверить страницы `Устройства`, `Конфигурации`, `Планировщик задач` и `Учетные данные`.
5. Открыть страницу профиля устройства и проверить кнопку `Терминал`.

#### 13. Запустить планировщик задач отдельно

Чтобы вручную выполнить все просроченные задачи один раз, нужно выполнить:

```bash
cd /home/andrew/bsuir/diploma
make run-due-tasks
```

Чтобы запустить постоянный локальный цикл планировщика без web-процесса, нужно выполнить:

```bash
cd /home/andrew/bsuir/diploma
make run-scheduler
```

Чтобы изменить интервал цикла, нужно передать `SCHEDULER_INTERVAL`:

```bash
make run-scheduler SCHEDULER_INTERVAL=30
```

Для периодического запуска через cron нужно добавить:

```bash
* * * * * cd /home/andrew/bsuir/diploma/netbox/netbox && /home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py run_due_tasks >> /tmp/config-weaver.log 2>&1
```

#### 14. Production-вариант

В production не нужно использовать `runserver --insecure`. Нужно:

1. Выполнить `collectstatic --noinput`.
2. Запустить HTTP-часть NetBox через gunicorn/uwsgi или ASGI-часть через Daphne/Uvicorn, если нужен WebSocket-терминал.
3. Настроить nginx или другой HTTP-сервер на раздачу `STATIC_ROOT`.
4. Проксировать обычные HTTP-запросы в backend NetBox.
5. Проксировать `/ws/` в ASGI backend с WebSocket upgrade-заголовками.
6. Запустить отдельный NetBox RQ worker.
7. Запустить `run_due_tasks` через cron/systemd timer или отдельный service loop.

Пример systemd-сервиса:

```ini
[Unit]
Description=NetBox with config-weaver plugin
After=network.target

[Service]
Type=notify
User=netbox
Group=netbox
WorkingDirectory=/home/andrew/bsuir/diploma/netbox/netbox
Environment="PATH=/home/andrew/bsuir/diploma/netbox/venv/bin"
ExecStart=/home/andrew/bsuir/diploma/netbox/venv/bin/gunicorn --bind 127.0.0.1:8001 netbox.wsgi

[Install]
WantedBy=multi-user.target
```

#### 15. Частые проблемы запуска

Ошибка статики в браузере:

- Выполнить `collectstatic --noinput`.
- Для локального запуска использовать `make run` или `make run-web`.
- Если используется WSGI `runserver` при `DEBUG = False`, запускать его только через `make run-wsgi`, где есть `--insecure`.
- Проверить `curl -I http://127.0.0.1:8000/static/netbox.css`.

Ошибка WebSocket-соединения в терминале:

- Проверить, что NetBox запущен через `make run` или `make run-web`, а не через `manage.py runserver`.
- Проверить, что `/ws/plugins/config-weaver/devices/<pk>/terminal/` не возвращает `404` от `WSGIServer`.
- Проверить, что пользователь авторизован и имеет право `change_deviceplatformprofile`.
- Проверить, что `DevicePlatformProfile` включен, содержит `management_ip` и связан с активными `DeviceCredential`.
- Проверить SSH-доступность устройства: `ssh <username>@<management_ip>`.
- Для reverse proxy проверить upgrade-заголовки WebSocket и совпадение `ws://`/`wss://` с HTTP/HTTPS.

Ошибка подключения к Redis:

- Проверить `redis-cli ping`.
- Убедиться, что Redis слушает `localhost:6379`.

Ошибка подключения к PostgreSQL:

- Проверить имя базы, пользователя и пароль в `configuration.py`.
- Убедиться, что пользователь `netbox` имеет права на базу `netbox`.

Плагин не появился:

- Проверить `PLUGINS = ['main']`.
- Проверить установку: `python -m pip show netbox-config-weaver`.
- Выполнить `python manage.py check`.
- Перезапустить NetBox.

#### 16. Переменные окружения

Для более безопасной конфигурации можно хранить секреты в окружении:

```bash
export NETBOX_SECRET_KEY='your-very-secret-key'
export CONFIG_WEAVER_SECRET_KEY='config-weaver-secret-key'
export CONFIG_WEAVER_VCS_REPO='/home/andrew/bsuir/diploma/config-weaver-vcs'
```

И использовать их в `configuration.py`:

```python
import os

SECRET_KEY = os.getenv('NETBOX_SECRET_KEY')

PLUGINS_CONFIG = {
    'main': {
        'secret_key': os.getenv('CONFIG_WEAVER_SECRET_KEY', 'change-this'),
        'vcs_repo_path': os.getenv('CONFIG_WEAVER_VCS_REPO'),
        'scheduler_max_workers': 8,
    }
}
```

### Структура проекта

- `main/domain/` — доменный слой: разбор YAML-плана, генерация и валидация команд, редактирование секретов.
- `main/application/` — слой сценариев использования: выполнение задач, preview команд, конфигурации, UML preview.
- `main/infrastructure/` — внешние адаптеры: SSH/Netmiko/Paramiko, Git VCS, Fernet-шифрование, ORM-репозитории.
- `main/presentation/` — UI-адаптер NetBox: формы, фильтры, таблицы, HTML views.
- `main/api/` — REST API-адаптер.
- `main/models.py` — Django/NetBox модели плагина.
- `main/management/commands/` — management-команды.
- `main/migrations/` — одна начальная миграция `0001_initial.py`.
- `main/templates/main/` — шаблоны UI NetBox.

### Что делает плагин

- Управляет конфигурациями сетевых устройств (Cisco, D-Link)
- Генерирует команды из сетевых задач
- Применяет команды к устройствам
- Делает резервные копии конфигураций в Git
- Поддерживает система версий с просмотром дифов между версиями
- Поддерживает автоматическое создание версий при отправке конфига на устройство
- Поддерживает планировщик задач и автозапуск
- Хранит UML-конфигурации (PlantUML/Mermaid/JSON)
- Кеширует тяжелые операции (парсинг, шаблоны, preview)

### Описание классов плагина

#### `main/__init__.py`

`NetBoxConfigWeaverConfig` — конфигурация NetBox-плагина.
- Атрибуты: `name`, `verbose_name`, `description`, `version`, `author`, `author_email`, `base_url`, `required_settings`, `default_settings`, `min_version`, `max_version`.
- Методы: собственных методов нет; класс используется NetBox для регистрации плагина.

#### `main/apps.py`

`NetboxConfigWeaverAppConfig` — Django `AppConfig` для приложения.
- Атрибуты: `default_auto_field`, `name`, `verbose_name`.
- Методы: собственных методов нет.

#### `main/models.py`

`DeviceCredential` — учетные данные для подключения к сетевому устройству.
- Поля и атрибуты: `AUTH_PASSWORD`, `AUTH_CHOICES`, `name`, `auth_method`, `username`, `password`, `enable_secret`, `ssh_port`, `timeout`, `use_enable`, `is_active`.
- Методы: `__str__()` возвращает имя credential; `password_plain` расшифровывает пароль; `enable_secret_plain` расшифровывает enable secret; `save()` шифрует секреты перед сохранением.

`CommandTemplate` — шаблон CLI-команды под вендора, платформу и тип операции.
- Поля и атрибуты: `OP_INTERFACE`, `OP_VLAN`, `OP_IP`, `OP_CUSTOM`, `OP_CHOICES`, `name`, `vendor`, `platform`, `operation_type`, `command_body`, `is_active`, `revision`.
- Методы: `__str__()` возвращает читаемое имя шаблона; `render(params)` подставляет параметры в `command_body`.

`NetworkTask` — описание сетевой задачи и YAML-плана конфигурации.
- Поля и атрибуты: `PLAN_YAML`, `PLAN_CHOICES`, `name`, `description`, `device_task`, `plan_format`, `plan_yaml`, `plan_checksum`, `enabled`, `last_validated_at`.
- Методы: `__str__()` возвращает имя задачи; `short_description` возвращает первые 100 символов описания.

`ConfigurationBackup` — версия сохраненной конфигурации устройства.
- Поля и атрибуты: `device`, `task`, `version`, `version_name`, `config_text`, `source`, `commit_hash`, `config_checksum`, `redacted`.
- Методы: `__str__()` возвращает устройство и номер версии.

`DevicePlatformProfile` — профиль устройства: вендор, платформа, management IP и credential.
- Поля и атрибуты: `VENDOR_CISCO`, `VENDOR_DLINK`, `VENDOR_CHOICES`, `PLATFORM_CISCO_IOS`, `PLATFORM_CISCO_XE`, `PLATFORM_CISCO_NXOS`, `PLATFORM_DLINK_DS`, `PLATFORM_DLINK_DGS`, `PLATFORM_CHOICES`, `device`, `credential`, `vendor`, `platform`, `management_ip`, `command_timeout`, `enabled`.
- Методы: `__str__()` возвращает устройство и платформу; `clean()` проверяет соответствие платформы выбранному вендору.

`ScheduledTask` — задача планировщика для применения сценария, сохранения конфигурации или healthcheck.
- Поля и атрибуты: `TYPE_APPLY_SCENARIO`, `TYPE_BACKUP`, `TYPE_HEALTHCHECK`, `TYPE_CHOICES`, `STATUS_PENDING`, `STATUS_RUNNING`, `STATUS_SUCCESS`, `STATUS_FAILED`, `STATUS_CHOICES`, `task_name`, `task_type`, `target_device`, `task`, `schedule_time`, `status`, `result_message`, `run_every_seconds`, `last_run_at`, `max_retries`, `retry_count`.
- Методы: `__str__()` возвращает имя задачи; `is_due()` проверяет, пора ли запускать задачу; `update_status(status, message)` обновляет статус, сообщение и время последнего запуска.

`UMLConfiguration` — сохраненное UML/Mermaid/JSON описание, связанное с задачей или устройством.
- Поля и атрибуты: `TYPE_PLANTUML`, `TYPE_MERMAID`, `TYPE_JSON`, `TYPE_CHOICES`, `name`, `diagram_type`, `task`, `device`, `source_text`, `rendered_svg`, `checksum`, `revision`, `is_active`.
- Методы: `__str__()` возвращает имя и ревизию.

#### `main/domain/configuration.py`

`ConfigValidationError` — доменное исключение ошибок плана или команд.
- Поля и атрибуты: наследует стандартные атрибуты `Exception`.
- Методы: собственных методов нет.

`NetworkPlanParser` — парсер и нормализатор YAML-плана.
- Поля и атрибуты: `INTERFACE_ALIASES`.
- Методы: `parse_plan(raw_yaml)` возвращает словарь из YAML; `normalize_interfaces(config)` раскрывает короткие имена интерфейсов и валидирует структуру.

`CommandGenerator` — генератор CLI-команд из плана и шаблонов.
- Поля и атрибуты: собственных атрибутов нет.
- Методы: `generate_interface_config(interface)` строит команды для интерфейса; `_resolve_template_key(operation, profile)` выбирает ключ шаблона; `generate_commands(plan, templates, profile)` возвращает общий список команд.

`ConfigurationValidator` — валидатор команд перед применением.
- Поля и атрибуты: `FORBIDDEN_PATTERNS`.
- Методы: `validate_commands(commands)` возвращает `(is_valid, errors)`.

#### `main/domain/security.py`

`SENSITIVE_PATTERNS` — набор регулярных выражений для поиска секретов.

Функция `redact_secrets(text)` заменяет найденные пароли, secret и SNMP community на `<REDACTED>`.

#### `main/application/backups.py`

`ConfigurationService` — use case для сохранения и сравнения конфигураций.
- Поля и атрибуты: собственных атрибутов нет.
- Методы: `save_backup(device, config_text, task=None)` сохраняет конфигурацию через VCS-адаптер; `compare_versions(first, second)` возвращает unified diff.

#### `main/application/tasks.py`

`TaskExecutor` — use case выполнения задач планировщика.
- Поля и атрибуты: собственных атрибутов нет.
- Методы: `preview_commands(task)` строит команды без применения; `_apply_commands(profile, task, commands)` применяет команды и сохраняет конфигурацию; `_run_apply_scenario(task)` запускает задачу применения; `_run_backup(task)` сохраняет конфигурацию; `_run_healthcheck(task)` проверяет SSH-сессию; `restore_backup_to_device(backup)` активирует выбранную конфигурацию на устройстве; `_reschedule_if_periodic(task)` переносит периодическую задачу; `run_task(task)` выполняет задачу с retry-логикой; `run_due_tasks()` запускает все просроченные задачи.

#### `main/application/uml.py`

`UMLConfigurationService` — use case для UML-конфигураций.
- Поля и атрибуты: собственных атрибутов нет.
- Методы: `calculate_checksum(source_text)` считает SHA-256; `save_with_checksum(uml)` сохраняет UML с checksum; `render_preview(uml)` возвращает SVG-preview.

#### `main/infrastructure/crypto.py`

Функция `_derive_key(raw)` получает Fernet-ключ из строки.

Функция `_get_fernet()` создает Fernet из `PLUGINS_CONFIG['main']['secret_key']`.

Функция `is_encrypted(value)` проверяет префикс `enc::`.

Функция `encrypt_value(value)` шифрует непустое значение.

Функция `decrypt_value(value)` расшифровывает значение и выбрасывает `RuntimeError` при неверном ключе.

#### `main/infrastructure/network.py`

`ConnectionSessionError` — исключение ошибок подключения.
- Поля и атрибуты: наследует стандартные атрибуты `Exception`.
- Методы: собственных методов нет.

`ConnectionSession` — адаптер SSH-сессии поверх Netmiko/Paramiko.
- Поля и атрибуты: `NETMIKO_DEVICE_MAP`, `RUNNING_CONFIG_COMMANDS`, `SAVE_COMMANDS`, `session`, `backend`, `platform`.
- Методы: `__init__()` инициализирует пустую сессию; `connect(host, platform, credential, prefer='netmiko')` подключается к устройству; `_connect_netmiko(params, credential)` создает Netmiko-сессию; `_connect_paramiko(params)` создает Paramiko-сессию; `disconnect()` закрывает сессию; `is_alive()` проверяет активность; `send_config_set(commands)` применяет команды и сохраняет конфигурацию; `get_running_config()` читает running-config.

`DeviceConnectionManager` — инфраструктурный сервис профиля и синхронизации running-config.
- Поля и атрибуты: собственных атрибутов нет.
- Методы: `get_profile(device)` возвращает активный профиль устройства; `should_verify_saved_config(device)` решает, нужна ли проверка сохраненной конфигурации; `verify_and_sync_running_config(device, running_config)` сохраняет контрольную конфигурацию при отсутствии версии или drift.

Функция `connect_device_cli(device, prefer='netmiko', verify_saved_config=True)` возвращает `(session, profile, check_result)`.

#### `main/infrastructure/repositories.py`

`ConfigurationRepository` — ORM-репозиторий для шаблонов и конфигураций.
- Поля и атрибуты: собственных атрибутов нет.
- Методы: `latest_backup_for_device(device_id)` возвращает последнюю версию; `compare_versions(first, second)` возвращает unified diff; `active_templates()` возвращает активные шаблоны с кешированием.

#### `main/infrastructure/vcs.py`

`BackupWriteResult` — dataclass результата записи конфигурации.
- Поля: `version`, `commit_hash`, `file_name`.
- Методы: dataclass-методы создаются автоматически.

`ConfigurationVCS` — Git-backed адаптер хранения версий конфигураций.
- Поля и атрибуты: собственных атрибутов нет.
- Методы: `repo_path()` возвращает и инициализирует Git-репозиторий; `safe_file_name(raw)` нормализует имя файла; `next_version(device)` вычисляет следующий номер версии; `build_version_name(device, dt=None)` строит имя версии; `write_backup(device, config_text, task=None, source='runtime')` пишет JSON в Git и создает `ConfigurationBackup` в БД.

#### `main/presentation/forms.py`

`DeviceCredentialForm` — UI-форма учетных данных.
- Поля и атрибуты: `password`, `enable_secret`, поля модели из `Meta.fields`.
- Методы: `__init__()` делает пароль необязательным при редактировании; `clean()` сохраняет старые секреты, если новые не введены.

`DevicePlatformProfileForm` — UI-форма профиля устройства.
- Поля и атрибуты: `device`, `credential`, поля модели из `Meta.fields`.
- Методы: собственных методов нет.

`CommandTemplateForm`, `NetworkTaskForm`, `ConfigurationBackupForm`, `ScheduledTaskForm`, `UMLConfigurationForm` — UI-формы соответствующих моделей.
- Поля и атрибуты: наборы `Meta.fields`; у `ScheduledTaskForm` есть `target_device` и `task`.
- Методы: собственных методов нет.

#### `main/presentation/filtersets.py`

`DeviceCredentialFilterSet`, `DevicePlatformProfileFilterSet`, `CommandTemplateFilterSet`, `ConfigurationBackupFilterSet`, `UMLConfigurationFilterSet` — фильтры UI/API для соответствующих моделей.
- Поля и атрибуты: `Meta.model`, `Meta.fields`.
- Методы: собственных методов нет.

`NetworkTaskFilterSet` — фильтр сетевых задач.
- Поля и атрибуты: `Meta.model`, `Meta.fields`.
- Методы: `search(queryset, name, value)` ищет по имени, описанию и `device_task`.

`ScheduledTaskFilterSet` — фильтр задач планировщика.
- Поля и атрибуты: `Meta.model`, `Meta.fields`.
- Методы: `search(queryset, name, value)` ищет по имени задачи и сообщению результата.

#### `main/presentation/tables.py`

`DeviceCredentialTable`, `CommandTemplateTable`, `NetworkTaskTable`, `ConfigurationBackupTable`, `DevicePlatformProfileTable`, `ScheduledTaskTable`, `UMLConfigurationTable` — таблицы NetBox UI.
- Поля и атрибуты: `Meta.model`, `Meta.fields`.
- Методы: собственных методов нет.

#### `main/presentation/views.py`

List/detail/edit/delete классы `DeviceCredential*`, `DevicePlatformProfile*`, `CommandTemplate*`, `NetworkTask*`, `ConfigurationBackup*`, `ScheduledTask*`, `UMLConfiguration*` — стандартные NetBox views.
- Поля и атрибуты: `queryset`, `table`, `filterset`, `form` в зависимости от типа view.
- Методы: собственных методов нет, кроме наследуемых NetBox generic views.

`ConfigurationBackupRestoreView` — action view активации сохраненной конфигурации.
- Методы: `post(request, pk)` запускает активацию и возвращает пользователя на страницу конфигурации.

`ConfigurationVersionListView` — view списка версий устройства.
- Поля и атрибуты: `template_name`.
- Методы: `get_context_data(**kwargs)` добавляет устройство и список версий.

`ConfigurationVersionDiffView` — view сравнения двух версий.
- Поля и атрибуты: `template_name`.
- Методы: `get_context_data(**kwargs)` добавляет diff или ошибку параметров.

`ScheduledTaskRunNowView` — action view ручного запуска задачи.
- Методы: `post(request, pk)` требует подтверждение создания версии и запускает задачу.

`ScheduledTaskPreviewView` — view preview команд.
- Поля и атрибуты: `template_name`.
- Методы: `get_context_data(**kwargs)` добавляет команды или ошибки preview.

`UMLConfigurationRenderView` — action view генерации SVG preview.
- Методы: `post(request, pk)` обновляет `rendered_svg` и checksum.

`UMLConfigurationPreviewView` — view просмотра SVG preview.
- Поля и атрибуты: `template_name`.
- Методы: `get_context_data(**kwargs)` добавляет UML-объект и SVG.

#### `main/api/serializers.py`

`DeviceCredentialSerializer` — DRF-сериализатор credential.
- Поля и атрибуты: `password`, `enable_secret` как `write_only`, `Meta.model`, `Meta.fields`.
- Методы: собственных методов нет.

`CommandTemplateSerializer`, `DevicePlatformProfileSerializer`, `NetworkTaskSerializer`, `ConfigurationBackupSerializer`, `ScheduledTaskSerializer`, `UMLConfigurationSerializer` — DRF-сериализаторы моделей.
- Поля и атрибуты: `Meta.model`, `Meta.fields`.
- Методы: собственных методов нет.

#### `main/api/views.py`

`DeviceCredentialViewSet`, `CommandTemplateViewSet`, `DevicePlatformProfileViewSet`, `NetworkTaskViewSet`, `ScheduledTaskViewSet`, `UMLConfigurationViewSet` — CRUD API viewset-классы.
- Поля и атрибуты: `queryset`, `serializer_class`.
- Методы: наследуют CRUD-поведение `NetBoxModelViewSet`.

`ConfigurationBackupViewSet` — CRUD API viewset для конфигураций и версий.
- Поля и атрибуты: `queryset`, `serializer_class`.
- Методы: `by_device(request)` возвращает версии одного устройства; `compare(request)` сравнивает две версии и возвращает diff.

#### `main/api/urls.py`, `main/urls.py`, `main/navigation.py`

Эти модули не объявляют собственных классов. Они регистрируют REST endpoints, HTML routes и меню NetBox.

#### `main/management/commands/run_due_tasks.py`

`Command` — Django management command для запуска просроченных задач.
- Поля и атрибуты: `help`.
- Методы: `handle(*args, **options)` запускает `TaskExecutor.run_due_tasks()` и печатает количество выполненных задач.

### Security hardening

- Credentials encrypted at rest (`password`, `enable_secret`)
- Secret redaction before backup persistence
- Write-only API fields for credential secrets
- Required plugin secret in `PLUGINS_CONFIG['main']['secret_key']`

### Caching

- Parsed plan cache by content hash
- Active templates cache
- Device profile cache
- Preview commands cache per scheduled task and network task revision

### Dependencies

- `Django` / NetBox plugin API
- `PyYAML`
- `netmiko`
- `paramiko`
- `cryptography`
- system `git` CLI

### Runtime scheduler

```bash
cd /home/andrew/bsuir/diploma
make run-due-tasks
```

Чтобы запустить постоянный локальный цикл scheduler, нужно выполнить:

```bash
cd /home/andrew/bsuir/diploma
make run-scheduler
```

Планировщик выполняет просроченные задачи в ограниченном thread pool. По умолчанию можно запускать до 8 задач параллельно. Чтобы изменить лимит, нужно задать `PLUGINS_CONFIG['main']['scheduler_max_workers']`; невалидные значения сбрасываются на 8, значения меньше 1 считаются равными 1.

### Version System

Основные возможности:

- **Автоматическое создание версий**: Каждый раз конфигурация отправляется на устройство или выполняется ручное резервное копирование, автоматически сохраняется новая версия в базе данных и Git.

- **Наименование версий**: Каждая версия получает автоматически генерируемое имя формата: **YYYY-MM-DD-HH-MM-device_name**
  - Пример: `2026-04-28-14-35-switch-core-01`
  - Время генерируется в UTC и сохраняется в JSON файлах Git репозитория
  - При совпадении имени для одного устройства добавляется суффикс `_1`, `_2`, `_3` и далее.
  - Если имя приближается к лимиту поля, базовая часть обрезается так, чтобы итоговое имя с суффиксом помещалось в `128` символов.

- **Просмотр версий**: В UI доступна таблица всех версий для текущего устройства с сортировкой по времени создания (новейшие выше).

- **Просмотр YAML**: На странице конкретной конфигурации доступна кнопка `Просмотреть YAML`. Она открывает YAML-представление версии с метаданными и многострочным `config`.

- **Наглядное сравнение конфигураций**: Чтобы построить unified diff, нужно выбрать две версии; строки отображаются с префиксами `+`, `-`, ` ` и `@@`.

- **Подтверждение на исполнение**: Процесс на исполнение задач в UI требует утверждение через чекбокс `confirm_create_version`.

#### API для работы с версиями

**Получить все версии для устройства:**

```
GET /api/plugins/main/configurations/by_device/?device_id=123
```

**Сравнить две версии:**

```
GET /api/plugins/main/configurations/compare/?from=1&to=2
```

#### Git репозиторий

Данные во всех версиях сохраняются в Git репозитории (JSON файлы) с commit-сообщениями в формате: `backup(device_name): version N`

Конфигурация сохраняется в JSON с полями: device, version, version_name, saved_at, task, source, config (redacted)

### Решение проблем

#### Плагин не появляется в меню NetBox

1. Проверить, что `main` добавлен в список `PLUGINS` в `configuration.py`.
2. Выполнить миграции: `python manage.py migrate main`.
3. Перезапустить NetBox через `make run` или production service.
4. Проверить логи: `journalctl -u netbox -n 50`.

#### Ошибка при подключении к устройству

- **Connection refused**: проверить IP-адрес и SSH-порт в `DevicePlatformProfile`.
- **Authentication failed**: проверить учетные данные в `DeviceCredential`.
- **Timeout**: увеличить `timeout` в credential или проверить сетевую доступность.

#### Ошибка WebSocket-соединения в терминале

Чтобы терминал работал, нужно запускать web-процесс через ASGI/Daphne. Для локального стенда нужно использовать:

```bash
cd /home/andrew/bsuir/diploma
make run
```

или, если нужен только web-процесс:

```bash
make run-web
```

Диагностировать нужно так:

1. Проверить, что процесс на `8000` - Daphne, а не `WSGIServer`.
2. Проверить, что прямой WebSocket handshake на `/ws/plugins/config-weaver/devices/<pk>/terminal/` без cookie возвращает `403 Access denied`, а не `404 Not Found`.
3. Проверить авторизацию пользователя в NetBox и право `change_deviceplatformprofile`.
4. Проверить `management_ip`, `ssh_port`, `username`, пароль и активность credential.
5. При reverse proxy проверить `Upgrade` и `Connection` headers.

Важно: `manage.py runserver` обслуживает только WSGI/HTTP и не должен использоваться для терминала. При `runserver` UI может открыться, но WebSocket будет падать.

#### Git репозиторий не инициализируется

Убедиться, что директория настроена правильно и у пользователя есть права на запись:

```bash
# Если директория не существует, она создастся автоматически
# Проверить права доступа
mkdir -p /home/andrew/bsuir/diploma/config-weaver-vcs
chmod 755 /home/andrew/bsuir/diploma/config-weaver-vcs
```

#### Ошибка при работе с YAML планом

```
ConfigValidationError: YAML parsing error...
```

1. Проверить синтаксис YAML в тексте плана.
2. Убедиться, что структура соответствует ожидаемому формату.
3. Проверить кодировку файла: должна быть `UTF-8`.

#### Задачи не запускаются по расписанию

1. Проверить, что запущен `make run`, `make run-scheduler`, cron или systemd timer.
2. Убедиться, что время сервера синхронизировано через NTP.
3. Проверить статус задач в UI: задача в статусе `PENDING` должна иметь время в прошлом.
4. Проверить логи: `journalctl -u config-weaver-tasks.timer`.

#### Высокое использование памяти

Плагин кеширует parsed plans и templates в памяти. Если памяти недостаточно:

```python
# В configuration.py отключите кеширование для плана
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'TIMEOUT': 300,  # 5 минут
    }
}
```

Или использовать Redis:

```python
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

### Примеры использования

#### Создание простой сетевой задачи (NetworkTask)

```yaml
# YAML план
interfaces:
  - name: "Gi0/0"
    description: "WAN uplink"
    ip: "203.0.113.1"
    netmask: "255.255.255.0"
    
vlans:
  - id: 100
    name: "Management"
  - id: 200
    name: "Users"
```

#### REST API примеры

```bash
# Получить все сетевые задачи
curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/main/tasks/

# Создать новую задачу (через UI удобнее)
curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -d '{
    "name": "core-switch-setup",
    "description": "Initial core switch config",
    "device_task": "core_config",
    "plan_yaml": "...",
    "enabled": true
  }' \
  http://netbox/api/plugins/main/tasks/

# Получить версии для устройства
curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/main/configurations/by_device/?device_id=1

# Сравнить две версии
curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/main/configurations/compare/?from=1&to=2
```
