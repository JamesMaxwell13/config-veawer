# Изменения NetBox для config-weaver

## Главное правило

Для нормальной работы модуля не нужно изменять основной код NetBox. Нужно держать все изменения внутри плагина `config-weaver`, конфигурации NetBox и локальных команд запуска.

## Что нужно настроить в NetBox

Чтобы подключить модуль, нужно изменить только конфигурацию NetBox:

```python
PLUGINS = ["main"]

PLUGINS_CONFIG = {
    "main": {
        "secret_key": "config-weaver-local-development-secret",
        "vcs_repo_path": "/home/andrew/bsuir/diploma/config-weaver-vcs",
        "scheduler_max_workers": 8,
    }
}
```

Также нужно настроить стандартные для NetBox зависимости:

- PostgreSQL в `DATABASES`;
- Redis в `REDIS['tasks']` и `REDIS['caching']`;
- `SECRET_KEY` и `API_TOKEN_PEPPERS`.

Эти настройки являются конфигурацией инсталляции, а не изменением core-кода NetBox.

## Что не нужно менять

Не нужно править файлы NetBox core:

- `netbox/netbox/settings.py`;
- `netbox/netbox/urls.py`;
- `netbox/netbox/views/*`;
- `netbox/dcim/*`;
- `netbox/templates/*`;
- другие файлы приложения NetBox.

Если для новой функции появляется необходимость менять core-код NetBox, сначала нужно описать причину, альтернативы и минимальный diff в этом файле. Без такого описания менять NetBox core нельзя.

## Нюанс WebSocket-терминала

Ручной терминал config-weaver работает через WebSocket и Channels. Обычный WSGI-запуск NetBox через `manage.py runserver` не обрабатывает `/ws/plugins/config-weaver/devices/<pk>/terminal/`.

Чтобы запустить терминал локально, нужно использовать ASGI entrypoint плагина:

```bash
cd /home/andrew/bsuir/diploma
make run
```

или только web-процесс:

```bash
make run-web
```

Этот запуск использует `main.asgi:application` из плагина. Внутри него:

- HTTP-запросы передаются в стандартный Django ASGI app NetBox;
- `/ws/...` передается в Channels `URLRouter`;
- локальная статика отдается через `ASGIStaticFilesHandler`.

Такой подход позволяет не менять `netbox/netbox/urls.py` и `netbox/netbox/settings.py`.

## Диагностика WebSocket

Чтобы проверить routing без браузера, нужно выполнить:

```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  http://127.0.0.1:8000/ws/plugins/config-weaver/devices/1/terminal/
```

Ожидаемые признаки:

- `403 Access denied` без cookie сессии - ASGI route работает, но пользователь не авторизован;
- `404 Not Found` от `WSGIServer` - запущен WSGI `runserver`, нужно перейти на `make run`;
- `Connection refused` - web-процесс не слушает порт;
- `400 bad Sec-WebSocket-Key` - тестовый WebSocket-заголовок некорректен.

## Production

В production нужно:

1. Раздавать `STATIC_ROOT` через nginx или другой HTTP-сервер.
2. Проксировать обычный HTTP в backend NetBox.
3. Проксировать `/ws/` в ASGI backend с WebSocket upgrade-заголовками.
4. Запустить отдельный NetBox RQ worker.
5. Запустить `run_due_tasks` через cron, systemd timer или отдельный service loop.

Пример обязательных nginx-заголовков для `/ws/`:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```
