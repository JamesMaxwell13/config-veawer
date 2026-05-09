# Изменения NetBox Для config-weaver

## Главное правило

Для работы `config-weaver` не нужно менять core-код NetBox.

Допустимые точки интеграции:

- `configuration.py` NetBox;
- установка Python-пакета плагина;
- локальные команды запуска;
- reverse proxy / systemd / cron в production.

Файлы NetBox core менять не нужно:

- `netbox/netbox/settings.py`;
- `netbox/netbox/urls.py`;
- `netbox/dcim/*`;
- `netbox/templates/*`;
- другие upstream-файлы NetBox.

Если будущая функция действительно потребует core-diff, сначала нужно описать причину, альтернативы и минимальный diff в этом документе.

## Подключение Плагина

Добавить в NetBox `configuration.py`:

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

Важно:

- `main` - имя Django app/plugin config.
- `config-weaver` - публичный `base_url` плагина.
- UI routes находятся под `/plugins/config-weaver/`.
- REST API находится под `/api/plugins/config-weaver/`.

Полный пример конфигурации: `examples/netbox_plugin_configuration.py`.

## Установка Пакета

Плагин ставится в virtualenv NetBox в editable-режиме:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip install -e \
  /home/andrew/bsuir/diploma/config-weaver
```

Проверка установленного пакета:

```bash
/home/andrew/bsuir/diploma/netbox/venv/bin/python -m pip show config-weaver
```

Для локального окружения можно использовать `Makefile` из `/home/andrew/bsuir/diploma`:

```bash
make deps
make install-plugin
make verify-plugin
make migrate
make collectstatic
```

## Актуальные URL

UI:

```text
/plugins/config-weaver/devices/
/plugins/config-weaver/credentials/
/plugins/config-weaver/configurations/
/plugins/config-weaver/network-tasks/
/plugins/config-weaver/tasks/
/plugins/config-weaver/templates/
/plugins/config-weaver/gitlab/
/plugins/config-weaver/gitlab/mappings/
/plugins/config-weaver/gitlab/logs/
/plugins/config-weaver/uml/
```

REST API:

```text
/api/plugins/config-weaver/devices/
/api/plugins/config-weaver/credentials/
/api/plugins/config-weaver/configurations/
/api/plugins/config-weaver/tasks/
/api/plugins/config-weaver/scheduled-tasks/
/api/plugins/config-weaver/templates/
/api/plugins/config-weaver/gitlab-integrations/
/api/plugins/config-weaver/gitlab-mappings/
/api/plugins/config-weaver/gitlab-sync-logs/
/api/plugins/config-weaver/gitlab/webhook/
/api/plugins/config-weaver/uml-configurations/
```

Swagger:

```text
/plugins/config-weaver/api/docs/
/plugins/config-weaver/api/schema/
```

WebSocket terminal:

```text
/ws/plugins/config-weaver/devices/<profile_id>/terminal/
```

## ASGI И Терминал

Ручной терминал работает через WebSocket и Channels.

`manage.py runserver` обслуживает WSGI/HTTP и не должен использоваться для проверки терминала.

Локально нужно запускать:

```bash
cd /home/andrew/bsuir/diploma
make run
```

или только web-процесс:

```bash
make run-web
```

Этот запуск использует `main.asgi:application` из плагина:

- HTTP-запросы передаются в стандартный Django ASGI app NetBox;
- `/ws/...` передается в Channels router;
- локальная статика отдается через ASGI static handler.

Такой подход оставляет маршрутизацию внутри плагина и не требует правок `netbox/netbox/urls.py`.

Если в NetBox задан `BASE_PATH`, WebSocket route учитывает этот префикс автоматически. Reverse proxy должен проксировать соответствующий `<BASE_PATH>/ws/` путь в ASGI backend.

## Диагностика WebSocket

```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  http://127.0.0.1:8000/ws/plugins/config-weaver/devices/1/terminal/
```

Ожидаемые признаки:

- `403 Access denied` без cookie сессии - ASGI route работает, пользователь не авторизован.
- `404 Not Found` от `WSGIServer` - запущен WSGI `runserver`; нужно использовать `make run` или `make run-web`.
- `Connection refused` - web-процесс не слушает порт.
- `400 bad Sec-WebSocket-Key` - некорректный тестовый WebSocket-заголовок.

## Production

В production нужно:

1. Раздавать `STATIC_ROOT` через nginx или другой HTTP-сервер.
2. Проксировать обычный HTTP в backend NetBox.
3. Проксировать `/ws/` в ASGI backend с WebSocket upgrade headers.
4. Запустить NetBox RQ worker.
5. Запустить `run_due_tasks` через cron, systemd timer или отдельный service loop.

GitLab webhook должен быть доступен по HTTPS endpoint:

```text
https://netbox.example.com/api/plugins/config-weaver/gitlab/webhook/
```

Webhook выполняет только импорт/постановку задачи. SSH-команды применяются планировщиком, поэтому worker и цикл `run_due_tasks` должны быть запущены отдельно.

Минимальные nginx headers для `/ws/`:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```
