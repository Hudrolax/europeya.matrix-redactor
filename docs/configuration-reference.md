# Конфигурация

## 1. Общий подход

Runtime-конфиг приходит через `.env`.

Конфигурация разделяется на четыре группы:

- подключение к `Synapse`;
- расписание и TTL;
- параметры HTTP-вызовов;
- локальное состояние приложения.

## 2. Обязательные переменные

### `SYNAPSE_BASE_URL`

Пример:

```env
SYNAPSE_BASE_URL=http://127.0.0.1:8008
```

Назначение:

- базовый URL Matrix Client API.

### `SYNAPSE_DB_URL`

Примеры:

```env
SYNAPSE_DB_URL=sqlite+pysqlite:////opt/synapse/homeserver.db
```

```env
SYNAPSE_DB_URL=postgresql+psycopg://synapse_ro:password@postgres:5432/synapse
```

Назначение:

- read-only подключение к базе `Synapse`.

### `TTL_HOURS`

Пример:

```env
TTL_HOURS=24
```

Назначение:

- возраст события, после которого оно попадает под redaction.

## 3. Расписание

### `CRON_SCHEDULE`

Пример:

```env
CRON_SCHEDULE=0 * * * *
```

Назначение:

- расписание запуска встроенного scheduler-процесса.

Примечание:

- частый запуск даёт более близкое к TTL поведение;
- запуск раз в сутки даёт только daily sweep.

### `TZ`

Пример:

```env
TZ=UTC
```

Назначение:

- timezone для scheduler и логов.

## 4. Режимы и поведение

### `DRY_RUN`

Пример:

```env
DRY_RUN=true
```

Назначение:

- если `true`, приложение считает и логирует кандидатов, но не отправляет redaction.

### `REDACTION_REASON`

Пример:

```env
REDACTION_REASON=Expired by policy
```

Назначение:

- текст причины, отправляемый в redaction event.

## 5. Производительность и retry policy

### `BATCH_SIZE`

Пример:

```env
BATCH_SIZE=200
```

### `REQUEST_TIMEOUT_SECONDS`

Пример:

```env
REQUEST_TIMEOUT_SECONDS=15
```

### `MAX_RETRIES`

Пример:

```env
MAX_RETRIES=3
```

### `RATE_LIMIT_SLEEP_MS`

Пример:

```env
RATE_LIMIT_SLEEP_MS=200
```

Назначение:

- дополнительная искусственная пауза между запросами;
- не заменяет встроенную обработку `429`.

## 6. Логирование и локальное состояние

### `LOG_LEVEL`

Пример:

```env
LOG_LEVEL=INFO
```

### `APP_STATE_DB_URL`

Пример:

```env
APP_STATE_DB_URL=sqlite+pysqlite:////app/var/state.db
```

### `LOCK_FILE_PATH`

Пример:

```env
LOCK_FILE_PATH=/app/var/run.lock
```

## 7. Отбор событий

### `EVENT_TYPE_ALLOWLIST`

Пример:

```env
EVENT_TYPE_ALLOWLIST=m.room.encrypted,m.room.message,m.reaction
```

Назначение:

- определяет набор event type, которые считаются пользовательскими сообщениями для redaction.

## 8. Дополнительная переменная compose

### `SYNAPSE_DATA_DIR`

Пример:

```env
SYNAPSE_DATA_DIR=./synapse-data
```

Назначение:

- путь к каталогу данных `Synapse` для `docker-compose` mount;
- приложением напрямую не читается и может безопасно игнорироваться кодом.

## 9. Актуальный `.env.example`

```env
SYNAPSE_DATA_DIR=./synapse-data
SYNAPSE_BASE_URL=http://127.0.0.1:8008
SYNAPSE_DB_URL=sqlite+pysqlite:////opt/synapse/homeserver.db
TTL_HOURS=24
CRON_SCHEDULE=0 * * * *
TZ=UTC
DRY_RUN=true
REDACTION_REASON=Expired by policy
BATCH_SIZE=200
REQUEST_TIMEOUT_SECONDS=15
MAX_RETRIES=3
RATE_LIMIT_SLEEP_MS=200
LOG_LEVEL=INFO
APP_STATE_DB_URL=sqlite+pysqlite:////app/var/state.db
LOCK_FILE_PATH=/app/var/run.lock
EVENT_TYPE_ALLOWLIST=m.room.encrypted,m.room.message,m.reaction
```

## 10. Инварианты старта

Приложение должно завершаться с ошибкой на старте, если:

- `SYNAPSE_BASE_URL` пустой;
- `SYNAPSE_DB_URL` пустой;
- `TTL_HOURS <= 0`;
- `BATCH_SIZE <= 0`;
- `CRON_SCHEDULE` синтаксически невалиден;
- `EVENT_TYPE_ALLOWLIST` пуст.

## 11. Необходимые внешние предпосылки

Текущая архитектура также предполагает, что в `Synapse DB` доступны:

- локальные пользователи в таблице `users`;
- токены пользователей в `access_tokens`;
- текущий membership через `current_state_events` и `room_memberships`.
