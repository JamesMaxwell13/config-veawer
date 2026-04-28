## config-weaver

Django/NetBox plugin for automated network configuration management.

### Установка и запуск

#### Требования

- NetBox 4.0+
- Python 3.10+
- Git (для работы с версиями конфигураций)

#### Установка плагина

1. **Скопируйте плагин в директорию plugins NetBox:**

```bash
# Перейдите в директорию с плагинами NetBox
cd /opt/netbox/netbox/plugins

# Клонируйте репозиторий (или скопируйте директорию)
git clone https://github.com/yourusername/config-weaver.git
# или просто скопируйте папку config-weaver
```

2. **Установите зависимости плагина:**

```bash
cd /opt/netbox
source venv/bin/activate
pip install pyyaml netmiko paramiko cryptography
```

3. **Добавьте плагин в конфигурацию NetBox:**

Отредактируйте `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = [
    'main',  # config-weaver плагин
]

PLUGINS_CONFIG = {
    'main': {
        # Обязательно: секретный ключ для шифрования credential
        'secret_key': 'your-secret-key-change-this',
        
        # Опционально: путь для Git репозитория версий
        'vcs_repo_path': '/opt/netbox/config-weaver-repo',
    }
}
```

4. **Выполните миграции:**

```bash
cd /opt/netbox/netbox
python manage.py migrate main
```

5. **Создайте суперпользователя (если нужно):**

```bash
python manage.py createsuperuser
```

#### Запуск NetBox с плагином

**Для разработки (development):**

```bash
cd /opt/netbox/netbox
python manage.py runserver 0.0.0.0:8000
```

NetBox будет доступен по адресу: `http://localhost:8000`

**Для production (с systemd и gunicorn):**

1. Добавьте плагин в список INSTALLED_APPS в `configuration.py` (если не добавляли через PLUGINS)

2. Соберите статические файлы:

```bash
cd /opt/netbox/netbox
python manage.py collectstatic --noinput
```

3. Создайте файл сервиса `/etc/systemd/system/netbox.service`:

```ini
[Unit]
Description=NetBox with config-weaver plugin
After=network.target

[Service]
Type=notify
User=netbox
Group=netbox
WorkingDirectory=/opt/netbox/netbox
Environment="PATH=/opt/netbox/venv/bin"
ExecStart=/opt/netbox/venv/bin/gunicorn --bind 0.0.0.0:8000 netbox.wsgi

[Install]
WantedBy=multi-user.target
```

4. Запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl start netbox
sudo systemctl enable netbox
```

#### Настройка планировщика задач

Для автоматического запуска просроченных задач добавьте cron:

```bash
# Отредактируйте crontab
crontab -e

# Добавьте строку (запуск каждую минуту)
* * * * * cd /opt/netbox/netbox && python manage.py run_due_tasks >> /var/log/config-weaver.log 2>&1
```

Или используйте systemd timer:

```ini
# /etc/systemd/system/config-weaver-tasks.service
[Unit]
Description=Config-Weaver Scheduled Tasks
After=network.target

[Service]
Type=oneshot
User=netbox
WorkingDirectory=/opt/netbox/netbox
Environment="PATH=/opt/netbox/venv/bin"
ExecStart=/opt/netbox/venv/bin/python manage.py run_due_tasks

# /etc/systemd/system/config-weaver-tasks.timer
[Unit]
Description=Run Config-Weaver Scheduled Tasks every minute
Requires=config-weaver-tasks.service

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

Активируйте timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable config-weaver-tasks.timer
sudo systemctl start config-weaver-tasks.timer
```

#### Проверка установки

1. Откройте NetBox в браузере: `http://localhost:8000`
2. Перейдите в Admin → Плагины → config-weaver
3. В боковом меню должен появиться пункт "config-weaver" с подменю для управления устройствами, задачами, бэкапами и т.д.

#### Переменные окружения

Для security лучше использовать переменные окружения вместо жестко закодированных значений:

```bash
export NETBOX_SECRET_KEY='your-very-secret-key'
export CONFIG_WEAVER_SECRET_KEY='config-weaver-secret-key'
export CONFIG_WEAVER_VCS_REPO='/path/to/git/repo'
```

Потом обновите `configuration.py`:

```python
import os

PLUGINS_CONFIG = {
    'main': {
        'secret_key': os.getenv('CONFIG_WEAVER_SECRET_KEY', 'change-this'),
        'vcs_repo_path': os.getenv('CONFIG_WEAVER_VCS_REPO'),
    }
}
```

### Project structure

- `main/` — основной пакет плагина (единая иерархия кода)
- `main/api/` — REST API
- `main/management/commands/` — management-команды
- `main/migrations/` — миграции
- `main/templates/main/` — шаблоны UI NetBox

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

### Описание классов по файлам (RU)

`main/models.py`
- `DeviceCredential`: учетные данные устройства, шифрование секретов, параметры SSH.
- `CommandTemplate`: шаблон CLI-команды для вендора/платформы/типа операции.
- `NetworkTask`: сетевая задача конфигурирования устройства (`device_task`, YAML-план, метаданные плана).
- `ConfigurationBackup`: версия сохраненной конфигурации (checksum, commit hash, redacted flag).
- `DevicePlatformProfile`: профиль привязки NetBox-устройства к вендору/платформе/credential.
- `ScheduledTask`: задача планировщика (тип, расписание, ретраи, статус, результат).
- `UMLConfiguration`: UML-описание инфраструктуры/задачи с версионностью.

`main/services.py`
- `ConnectionSession`: унифицированное подключение (Netmiko/Paramiko), чтение/применение конфигов.
- `NetworkPlanParser`: парсинг и нормализация YAML-планов (с кешированием).
- `CommandGenerator`: генерация CLI-команд из планов + шаблонов.
- `ConfigurationValidator`: валидация списка команд, запрет опасных команд.
- `ConfigurationBackupService`: запись бэкапов в Git + в БД, расчет контрольных сумм, сравнение версий.
- `TaskExecutor`: запуск задач (apply/backup/healthcheck), preview, retries, schedule.
- `UMLConfigurationService`: checksum и сервисные операции для UML-конфигураций.

`main/forms.py`
- `DeviceCredentialForm`: безопасная форма для credential (password fields + edit behavior).
- `DevicePlatformProfileForm`: форма профиля устройства.
- `CommandTemplateForm`: форма шаблона команды.
- `NetworkTaskForm`: форма сетевой задачи.
- `ConfigurationBackupForm`: форма бэкапа.
- `ScheduledTaskForm`: форма задач планировщика.
- `UMLConfigurationForm`: форма UML-конфигурации.

`main/filtersets.py`
- Набор filterset-классов для всех доменных сущностей, включая UML.

`main/tables.py`
- Набор table-классов для UI-таблиц всех сущностей, включая UML.

`main/views.py`
- UI-вьюхи list/detail/edit/delete по всем сущностям.
- Действия `Run now`, `Preview commands`, `Restore backup`.
- UML list/detail/edit/delete.

`main/urls.py`
- URL-маршруты UI для сущностей и действий.

`main/navigation.py`
- Пункты меню плагина в интерфейсе NetBox.

`main/api/serializers.py`
- DRF-сериализаторы для API-моделей (секреты credential — write-only).

`main/api/views.py`
- API viewset-классы для доменных сущностей.

`main/api/urls.py`
- API-роутер и endpoint-ы (`credentials`, `profiles`, `templates`, `tasks`, `backups`, `scheduled-tasks`, `uml-configurations`).
- Дополнительные endpoint-ы для работы с версиями:

`main/crypto.py`
- Шифрование/дешифрование секретов на Fernet.

`main/security.py`
- Редактирование чувствительных данных в конфигурациях перед сохранением.

`main/management/commands/run_due_tasks.py`
- Запуск просроченных задач планировщика.

### Security hardening

- Credentials encrypted at rest (`password`, `enable_secret`)
- Secret redaction before backup persistence
- Write-only API fields for credential secrets
- Required plugin secret in `PLUGINS_CONFIG['main']['secret_key']`

### Caching

- Parsed plan cache by content hash
- Active templates cache
- Device profile cache
- Preview commands cache per task/scenario revision

### Dependencies

- `Django` / NetBox plugin API
- `PyYAML`
- `netmiko`
- `paramiko`
- `cryptography`
- system `git` CLI

### Runtime scheduler

```bash
python manage.py run_due_tasks
```

### Version System

Основные возможности:

- **Автоматическое создание версий**: Каждый раз конфигурация отправляется на устройство или выполняется ручное резервное копирование, автоматически сохраняется новая версия в базе данных и Git.

- **Наименование версий**: Каждая версия отражается автоматически генерируемым именем формата: **YYYY-MM-DD-HH-MM-device_name**
  - Пример: `2026-04-28-14-35-switch-core-01`
  - Время генерируется в UTC и сохраняется в JSON файлах Git репозитория

- **Просмотр версий**: В UI доступна таблица всех версий для текущего устройства с сортировкой по времени создания (новейшие выше).

- **Наглядное сравнение конфигураций**: Выберите две версии для построения unified diff - строки изображены с префиксами `+`, `-`, ` ` и `@@`.

- **Подтверждение на исполнение**: Процесс на исполнение задач в UI требует утверждение через чекбокс `confirm_create_version`.

#### API для работы с версиями

**Получить все версии для устройства:**

```
GET /api/plugins/main/backups/by_device/?device_id=123
```

**Сравнить две версии:**

```
GET /api/plugins/main/backups/compare/?from=1&to=2
```

#### Git репозиторий

Данные во всех версиях сохраняются в Git репозитории (JSON файлы) с commit-сообщениями в формате: `backup(device_name): version N`

Конфигурация сохраняется в JSON с полями: device, version, version_name, saved_at, task, source, config (redacted)

### Решение проблем

#### Плагин не появляется в меню NetBox

1. Проверьте, что `main` добавлен в список `PLUGINS` в `configuration.py`
2. Выполните миграции: `python manage.py migrate main`
3. Перезагрузите NetBox: `systemctl restart netbox` или перезапустите `runserver`
4. Проверьте логи: `journalctl -u netbox -n 50`

#### Ошибка при подключении к устройству

- **Connection refused**: Проверьте IP адрес и SSH порт в `DevicePlatformProfile`
- **Authentication failed**: Проверьте учетные данные в `DeviceCredential`
- **Timeout**: Увеличьте `timeout` в credential или проверьте сетевую доступность

#### Git репозиторий не инициализируется

Убедитесь, что директория настроена правильно и у пользователя есть права на запись:

```bash
# Если директория не существует, она создастся автоматически
# Проверьте права доступа
chown -R netbox:netbox /opt/netbox/config-weaver-repo
chmod 755 /opt/netbox/config-weaver-repo
```

#### Ошибка при работе с YAML планом

```
ConfigValidationError: YAML parsing error...
```

1. Проверьте синтаксис YAML в план текста (используйте валидатор)
2. Убедитесь, что структура соответствует ожидаемому формату
3. Проверьте кодировку файла (должно быть UTF-8)

#### Задачи не запускаются по расписанию

1. Проверьте, что cron или systemd timer настроены правильно
2. Убедитесь, что время сервера синхронизировано (NTP)
3. Проверьте статус задач в UI: версия в статус `PENDING` должна иметь время в прошлом
4. Проверьте логи: `journalctl -u config-weaver-tasks.timer`

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

Или используйте Redis:

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
  http://netbox/api/plugins/main/backups/by_device/?device_id=1

# Сравнить две версии
curl -H "Authorization: Token YOUR_API_TOKEN" \
  http://netbox/api/plugins/main/backups/compare/?from=1&to=2
```
