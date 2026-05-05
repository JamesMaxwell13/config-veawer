# Туториал по шаблонам команд

В этой директории находится встроенный каталог команд Config Weaver.

- `cisco.yaml` содержит шаблоны команд Cisco.
- `dlink.yaml` содержит шаблоны команд D-Link.

Каталог не является полным справочником CLI-команд производителя. Это стартовый набор для типовых и повторяемых операций. Редкие разовые команды лучше добавлять через `raw_commands` или через пользовательские шаблоны в интерфейсе NetBox.

## Как загружаются шаблоны

Во время работы Config Weaver объединяет два источника:

1. Встроенные YAML-шаблоны из этой директории.
2. Активные объекты `CommandTemplate`, созданные через UI или API NetBox.

Если шаблон из базы данных имеет те же `vendor`, `platform`, `operation_type` и `name`, что и YAML-шаблон, используется шаблон из базы данных. Так можно переопределять встроенные команды без редактирования файлов плагина.

## Структура YAML-файла

Каждый файл производителя начинается с ключа `vendor` и списка `templates`:

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

Обязательные поля:

- `name`: стабильное имя операции, которое используется в `NetworkTask.plan_yaml`;
- `platform`: платформа из `DevicePlatformProfile`, например `cisco_ios` или `dlink_ds`;
- `operation_type`: группа операции: `interface`, `vlan`, `ip` или `custom`;
- `command_body`: одна или несколько CLI-команд, по одной команде на строку.

Рекомендуемые поля:

- `revision`: версия шаблона, увеличивай ее при изменениях;
- `description`: короткое описание назначения шаблона;
- `params`: список параметров, которые используются в `command_body`.

## Параметры шаблона

В `command_body` используются плейсхолдеры в фигурных скобках:

```yaml
command_body: |
  interface {interface}
  description {description}
```

Значения передаются из задачи:

```yaml
operations:
  - name: interface_description
    params:
      interface: GigabitEthernet0/1
      description: uplink-to-core
```

Если обязательного параметра нет, предпросмотр команд и выполнение задачи завершатся ошибкой до отправки команд на устройство.

## Как добавить шаблон Cisco

Добавь новый элемент в `cisco.yaml`:

```yaml
  - name: ospf_network
    platform: cisco_ios
    operation_type: custom
    revision: 1
    description: Add an OSPF network statement.
    params: [process_id, network, wildcard, area]
    command_body: |
      router ospf {process_id}
      network {network} {wildcard} area {area}
```

Используй его в `NetworkTask.plan_yaml`:

```yaml
operations:
  - name: ospf_network
    params:
      process_id: 1
      network: 10.0.0.0
      wildcard: 0.0.0.255
      area: 0
```

Итоговые команды:

```text
router ospf 1
network 10.0.0.0 0.0.0.255 area 0
```

## Как добавить шаблон D-Link

Добавь новый элемент в `dlink.yaml`:

```yaml
  - name: access_vlan_named
    platform: dlink_ds
    operation_type: vlan
    revision: 1
    description: Create VLAN and assign an untagged access port.
    params: [vlan_id, vlan_name, interface]
    command_body: |
      create vlan {vlan_name} tag {vlan_id}
      config vlan vlanid {vlan_id} add untagged {interface}
      config ports {interface} pvid {vlan_id}
```

Используй его в `NetworkTask.plan_yaml`:

```yaml
operations:
  - name: access_vlan_named
    params:
      vlan_id: 20
      vlan_name: USERS
      interface: 1:1
```

Итоговые команды:

```text
create vlan USERS tag 20
config vlan vlanid 20 add untagged 1:1
config ports 1:1 pvid 20
```

## Как добавить шаблон через NetBox UI

Используй UI, если команда специфична для твоей лаборатории или должна переопределить встроенный YAML-шаблон:

1. Открой `Config Weaver`.
2. Перейди в `Шаблоны команд`.
3. Нажми `Добавить шаблон команд`.
4. Заполни поля:
   - `name`;
   - `vendor`;
   - `platform`;
   - `operation_type`;
   - `command_body`;
   - `is_active`.
5. Сохрани шаблон.
6. Открой шаблон и нажми `Предпросмотр`, чтобы проверить параметры до запуска задачи.

Пример шаблона через UI:

```text
name: loopback_ip
vendor: cisco
platform: cisco_ios
operation_type: ip
command_body:
interface Loopback{number}
ip address {ip} {mask}
no shutdown
```

Использование в задаче:

```yaml
operations:
  - name: loopback_ip
    params:
      number: 10
      ip: 10.10.10.10
      mask: 255.255.255.255
```

## Raw-команды

`raw_commands` нужны для редких команд, для которых нет смысла создавать переиспользуемый шаблон:

```yaml
raw_commands:
  - do show version
  - do show ip interface brief
```

Raw-команды можно добавить и внутрь операции:

```yaml
operations:
  - raw_commands: |
      interface Loopback99
      description temporary-test
```

Raw-команды все равно проходят через валидатор команд.

## Правила безопасности

Валидатор блокирует опасные команды для лабораторной автоматизации, включая:

- `write erase`;
- `erase startup-config`;
- `delete flash:`;
- `no username`;
- `reload`;
- `format flash`.

Не добавляй разрушительные команды в YAML-файлы. Шаблоны должны описывать предсказуемые конфигурационные операции, которые безопасно просматривать и повторять.

## Чеклист нового шаблона

Перед сохранением или коммитом шаблона:

1. Выбери стабильное и понятное `name`.
2. Проверь, что `vendor` и `platform` совпадают с `DevicePlatformProfile`.
3. Перечисли все плейсхолдеры в `params`.
4. Пиши одну CLI-команду на строку в `command_body`.
5. Проверь шаблон через `Предпросмотр`.
6. Проверь итоговые команды через preview задачи `NetworkTask`.
7. Сначала запусти задачу на лабораторном устройстве, а не на реальном оборудовании.
