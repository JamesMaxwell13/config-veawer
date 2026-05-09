# config-weaver

`config-weaver` - плагин для NetBox 4.x, предназначенный для управления конфигурациями сетевых устройств.

Плагин добавляет профили подключения к устройствам, зашифрованные учётные данные, встроенный каталог и пользовательские шаблоны команд, сценарии команд, планировщик задач, резервные копии конфигураций, YAML-представление конфигураций, ручной WebSocket-терминал, локальное Git/VCS-хранилище версий, двустороннюю GitLab-синхронизацию desired state и Swagger UI для REST API.

## Документы

- `README.md` - установка, запуск, пользовательские сценарии и API.
- `README_NETBOX_CHANGE.md` - что нужно и не нужно менять в NetBox для работы плагина.
- `main/command_catalog/README.md` - формат встроенного каталога команд и правила добавления шаблонов.

## Структура Рабочего Каталога

Ожидаемая структура локального workspace:

```text
/home/andrew/bsuir/diploma/
├── config-weaver/      # исходный код плагина
├── config-weaver-vcs/  # опциональное Git-хранилище версий конфигураций
└── netbox/             # исходный код NetBox и virtualenv
```

Команды NetBox выполняются из:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
```

Команды, относящиеся к исходникам плагина, выполняются из:

```bash
cd /home/andrew/bsuir/diploma/config-weaver
```

## Требования

- NetBox 4.x, проверялось с локальным деревом NetBox 4.5.x.
- Python virtualenv: `/home/andrew/bsuir/diploma/netbox/venv`.
- PostgreSQL, настроенный для NetBox.
- Redis для задач и кеширования NetBox.
- Python-зависимости плагина: `pyyaml`, `netmiko`, `paramiko`, `cryptography`, `channels`, `daphne`.
- Установленный `git`, если требуется коммитить версии конфигураций в локальное VCS-хранилище.

## Установка

Установите runtime-зависимости в virtualenv NetBox:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install \
  pyyaml netmiko paramiko cryptography channels daphne
```

Установите плагин в editable-режиме:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install -e \
  /home/andrew/bsuir/diploma/config-weaver
```

Проверьте, что пакет доступен:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip show config-weaver
```

Те же действия можно выполнить через `Makefile` из рабочего каталога:

```bash
cd /home/andrew/bsuir/diploma
make setup
```

## Настройка NetBox

Добавьте плагин в `configuration.py`.

Имя Python-модуля плагина - `main`; публичный UI/API base URL - `config-weaver`.

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

Полный пример находится в `examples/netbox_plugin_configuration.py`.

`secret_key` обязателен. Он используется для шифрования секретов: паролей устройств, GitLab access token и GitLab webhook secret. Значение нужно сохранить стабильным: если изменить ключ после первого использования, ранее зашифрованные значения станут нечитаемыми.

`vcs_repo_path` необязателен. Если он не задан, плагин использует `MEDIA_ROOT/config_weaver_repo`.

`scheduler_max_workers` необязателен. Некорректные значения заменяются на `8`, значения меньше `1` считаются равными `1`.

## База Данных И Начальные Данные

Примените миграции:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py migrate
```

Синхронизируйте встроенные шаблоны команд:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py sync_command_templates
```

Предварительный просмотр синхронизации шаблонов без записи:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py sync_command_templates --dry-run
```

Базовая проверка Django:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py check
```

## Локальный Запуск

Используйте `Makefile` из `/home/andrew/bsuir/diploma`.

Запустить NetBox ASGI, RQ worker и цикл планировщика config-weaver:

```bash
cd /home/andrew/bsuir/diploma
make run
```

Запустить только ASGI web-процесс:

```bash
make run-web
```

Запустить только RQ worker:

```bash
make run-worker
```

Запустить только планировщик задач config-weaver:

```bash
make run-scheduler
```

Ручной терминал устройства требует ASGI/Daphne. Не используйте `manage.py runserver` для проверки терминала: он обслуживает только WSGI/HTTP и не поддерживает `/ws/plugins/config-weaver/...`.

## Интерфейс

После запуска плагин появляется в меню NetBox как `Config Weaver`.

Основные страницы:

- `/plugins/config-weaver/devices/` - профили подключения устройств.
- `/plugins/config-weaver/credentials/` - зашифрованные SSH-учётные данные.
- `/plugins/config-weaver/configurations/` - сохранённые конфигурации и backup-версии.
- `/plugins/config-weaver/network-tasks/` - reusable YAML-сценарии команд.
- `/plugins/config-weaver/gitlab/` - интеграции с GitLab.
- `/plugins/config-weaver/gitlab/mappings/` - связи устройств NetBox с файлами GitLab.
- `/plugins/config-weaver/gitlab/logs/` - журнал синхронизации GitLab.
- `/plugins/config-weaver/tasks/` - планировщик задач.
- `/plugins/config-weaver/templates/` - шаблоны команд.
- `/plugins/config-weaver/uml/` - UML-описания.
- `/plugins/config-weaver/api/docs/` - Swagger UI для REST API плагина.

На странице профиля устройства доступны действия `CLI`, `Версии`, `Получить конфигурацию` и `Терминал`. На странице backup-конфигурации доступны YAML-представление, refresh/drift-check и отправка выбранной версии на устройство.

Списковые страницы поддерживают стандартные NetBox bulk edit и bulk delete там, где это применимо.

## REST API И Swagger

Base URL REST API:

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

Примеры:

```bash
curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/config-weaver/devices/

curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/config-weaver/configurations/by_device/?device_id=1

curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/config-weaver/configurations/compare/?from=1\&to=2
```

Основные API resources:

- `/api/plugins/config-weaver/credentials/`
- `/api/plugins/config-weaver/devices/`
- `/api/plugins/config-weaver/templates/`
- `/api/plugins/config-weaver/tasks/` - `NetworkTask`, reusable сценарии команд.
- `/api/plugins/config-weaver/scheduled-tasks/` - задачи планировщика.
- `/api/plugins/config-weaver/configurations/`
- `/api/plugins/config-weaver/gitlab-integrations/`
- `/api/plugins/config-weaver/gitlab-mappings/`
- `/api/plugins/config-weaver/gitlab-sync-logs/`
- `/api/plugins/config-weaver/gitlab/webhook/`
- `/api/plugins/config-weaver/uml-configurations/`

Старые примеры `/api/plugins/main/...` неактуальны. NetBox регистрирует плагин по публичному `base_url = "config-weaver"`.

## Рабочий Процесс Конфигураций

1. Создайте `DeviceCredential`.
2. Создайте `DevicePlatformProfile` для устройства `dcim.Device`.
3. Нажмите `Получить конфигурацию` на странице профиля или на вкладке конфигураций устройства.
4. Плагин подключится к устройству, получит running-config, сохранит новую `ConfigurationBackup`, если содержимое изменилось, и перенаправит на `/plugins/config-weaver/configurations/<id>/`.
5. Страница конфигурации покажет YAML и доступные действия.

Если running-config не изменился, плагин перенаправит на текущую существующую backup-версию.

Обновление конфигурации использует профиль устройства и учётные данные. В тестовом окружении можно использовать обычные SSH-учётные данные, например `admin/admin`, но в production значения должны храниться только через `DeviceCredential`.

## YAML-Формат Конфигураций

Raw running-config преобразуется в YAML плагина.

Текущая версия схемы - `2`. Схема `1` остаётся читаемой для старых backup-версий.

Схема `2` разделяет:

- `operations` - глобальные команды, сопоставленные с шаблонами команд.
- `sections` - контекстные блоки, например `interface`, `line`, `router`, `ip access-list`, `gatekeeper` и похожие Cisco-секции.
- `raw_commands` - несопоставленные глобальные команды верхнего уровня.

Пример:

```yaml
schema_version: 2
device:
  id: 1
  name: sw-core-01
platform: cisco_ios
source: runtime
operations: []
sections:
  - header: interface GigabitEthernet0/1
    operations: []
    raw_commands:
      - description Uplink
      - no shutdown
raw_commands:
  - hostname sw-core-01
```

YAML также может содержать сценарий команд для `ScheduledTask`:

```yaml
interfaces:
  - name: gi0/1
    description: Uplink
    shutdown: false
operations:
  - name: access_vlan
    params:
      interface: GigabitEthernet0/1
      vlan_id: 10
```

Перед отправкой команд на устройство они проходят существующие этапы:

- `NetworkPlanParser`;
- `CommandGenerator`;
- `ConfigurationValidator`;
- добавление команды сохранения конфигурации для поддерживаемой платформы.

## Локальное VCS-Хранилище

Локальное Git/VCS-хранилище плагина не заменяется GitLab-интеграцией.

Его назначение:

- журнал фактически сохранённых конфигураций;
- backup-версии перед применением изменений;
- версии, созданные после успешного применения команд;
- локальная история, независимая от GitLab desired state.

GitLab используется как репозиторий желаемого состояния конфигураций устройств. Локальный VCS остаётся журналом фактических операций плагина.

## Интеграция С GitLab

Config Weaver поддерживает двустороннюю синхронизацию YAML-конфигураций устройств с GitLab Repository Files API.

GitLab хранит desired state, а плагин:

- импортирует изменённые YAML-файлы из GitLab;
- создаёт локальные `ConfigurationBackup` с source `gitlab`;
- связывает устройство NetBox с файлом через `GitLabConfigMapping`;
- может создать due-now `ScheduledTask` для применения конфигурации, если включён `auto_apply`;
- обновляет файл в GitLab при изменении конфигурации через интерфейс или API плагина;
- пишет результат каждой операции в `GitLabSyncLog`.

`NetworkTask` не синхронизируется с GitLab. Интеграция относится только к конфигурациям устройств.

### GitLab Project Access Token

Создайте Project Access Token в GitLab.

Рекомендуемый scope:

```text
api
```

На некоторых инсталляциях GitLab можно использовать более узкие права, если они позволяют читать и изменять Repository Files API.

Токен вводится в форме `GitLabIntegration` и хранится зашифрованным. Не указывайте token в логах, README, примерах payload или commit message.

### Пример GitLabIntegration

```text
name: Production GitLab
gitlab_url: https://gitlab.example.com
project_id: network/configs
branch: main
root_path: configs
file_path_pattern: {root_path}/{site_slug}/{location_slug}/{rack_slug}/{device_name}.yaml
enabled: true
auto_apply: false
```

`project_id` может быть числовым ID проекта или путём вида `group/project`, если GitLab API принимает такой идентификатор.

### Структура Репозитория GitLab

Файлы конфигураций строятся по данным размещения из основного NetBox:

```text
configs/
  <site_slug>/
    <location_slug>/
      <rack_name_or_slug>/
        <device_name>.yaml
```

Пример:

```text
configs/
  main-campus/
    building-a-floor-2/
      rack-12/
        sw-core-01.yaml
```

Если у устройства нет location или rack:

```text
configs/
  <site_slug>/
    no-location/
      no-rack/
        <device_name>.yaml
```

Если нет site:

```text
configs/
  no-site/
    no-location/
      no-rack/
        <device_name>.yaml
```

### Построение Пути К Файлу

Путь строит `GitLabPathBuilder`.

Он берёт:

- `device.site.slug` или `device.site.name`;
- `device.location.slug` или `device.location.name`;
- `device.rack.name` или `device.rack.slug`;
- `device.name`;
- дополнительные доступные атрибуты: role, platform, manufacturer, device ID.

Поддерживаемые placeholders:

```text
{root_path}
{site}
{site_slug}
{location}
{location_slug}
{rack}
{rack_slug}
{device}
{device_name}
{device_id}
{role}
{role_slug}
{platform}
{manufacturer}
```

Значение по умолчанию:

```text
{root_path}/{site_slug}/{location_slug}/{rack_slug}/{device_name}.yaml
```

Все части пути нормализуются:

- пробелы и недопустимые символы заменяются безопасным разделителем;
- `..`, `/`, `\` и path traversal не допускаются;
- пустые значения заменяются fallback-сегментами.

Fallback-сегменты:

```text
no-site
no-location
no-rack
no-role
no-platform
no-manufacturer
```

### GitLab Webhook

Webhook URL:

```text
https://netbox.example.com/api/plugins/config-weaver/gitlab/webhook/
```

Настройки в GitLab:

- Trigger: `Push events`.
- Secret token: значение `webhook_secret` из `GitLabIntegration`.
- Branch: ветка, указанная в `GitLabIntegration.branch`, например `main`.

Endpoint проверяет `X-Gitlab-Token`, игнорирует события из другой ветки и обрабатывает только `.yaml`/`.yml` файлы внутри `root_path`.

Пример поддерживаемого push payload:

```json
{
  "ref": "refs/heads/main",
  "checkout_sha": "abc123",
  "project": {
    "id": 42,
    "path_with_namespace": "network/configs"
  },
  "commits": [
    {
      "added": [],
      "modified": [
        "configs/main-campus/building-a-floor-2/rack-12/sw-core-01.yaml"
      ],
      "removed": []
    }
  ]
}
```

После webhook плагин:

1. Находит подходящую `GitLabIntegration`.
2. Проверяет branch и secret.
3. Находит изменённые YAML-файлы.
4. Сопоставляет файл с устройством NetBox через `GitLabConfigMapping` или через вычисленный путь.
5. Загружает raw YAML из GitLab по `checkout_sha`.
6. Валидирует YAML существующей логикой.
7. Создаёт `ConfigurationBackup` с source `gitlab`.
8. Обновляет mapping и commit SHA.
9. Пишет `GitLabSyncLog`.
10. Если `auto_apply=true`, создаёт due-now `ScheduledTask`.

SSH-команды не выполняются внутри HTTP webhook-запроса.

### Auto Apply

Если `auto_apply=false`, GitLab webhook только импортирует desired configuration в плагин.

Если `auto_apply=true`, webhook создаёт `ScheduledTask` со статусом `pending` и текущим временем запуска. Применение выполняет существующий планировщик.

Перед отправкой команд на устройство executor создаёт pre-apply backup текущей running configuration. После успешного применения создаётся новая backup-версия результата.

### Синхронизация Из Плагина В GitLab

При изменении `ConfigurationBackup` через UI или API плагин:

1. Определяет устройство из `ConfigurationBackup.device`.
2. Находит существующий `GitLabConfigMapping` или создаёт новый.
3. Строит путь по данным NetBox.
4. Получает metadata файла из GitLab.
5. Создаёт файл, если его ещё нет.
6. Обновляет файл, если он существует и нет конфликта commit SHA.
7. Обновляет `last_gitlab_commit_sha`.
8. Пишет `GitLabSyncLog`.

Commit message:

```text
Update config for <device_name> from NetBox Config Weaver
```

Изменения, пришедшие из GitLab webhook, не отправляются обратно в GitLab, чтобы избежать рекурсивной синхронизации GitLab -> plugin -> GitLab.

### Защита От Конфликтов

`GitLabConfigMapping.last_gitlab_commit_sha` хранит последний известный commit SHA файла.

Перед обновлением файла из плагина сервис получает metadata файла GitLab и сравнивает `last_commit_id` с сохранённым `last_gitlab_commit_sha`.

Если файл изменился в GitLab после последней синхронизации:

- файл не перезаписывается;
- создаётся `GitLabSyncLog` со статусом `conflict`;
- пользователю или API возвращается понятное сообщение об ошибке/конфликте.

Для webhook-событий GitLab считается источником истины.

## Безопасность

- `access_token` и `webhook_secret` хранятся зашифрованными.
- Секреты не должны попадать в логи.
- `PLUGINS_CONFIG["main"]["secret_key"]` должен быть длинным, случайным и стабильным.
- Для GitLab предпочтительнее Project Access Token вместо персонального token.
- Не включайте опасные команды в YAML. Команды проходят через `ConfigurationValidator`, который блокирует известные опасные операции.
- Не применяйте конфигурации без актуальных backup-версий.

## Команды Для Миграций И Тестов

Применить миграции:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py migrate
```

Проверить проект:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py check
```

Запустить тесты плагина:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main
```

Запустить только тесты GitLab-интеграции:

```bash
cd /home/andrew/bsuir/diploma/netbox/netbox
/home/andrew/bsuir/diploma/netbox/venv/bin/python manage.py test main.tests.test_gitlab_integration
```
