# Конфигурация

## 1. Общий подход

Весь runtime-конфиг должен приходить через `.env`.

Причины:

- это удобно для `docker-compose`;
- конфиг легко менять без пересборки image;
- один и тот же код может одинаково работать в SQLite и PostgreSQL режимах.

## 2. Обязательные переменные

### `SYNAPSE_BASE_URL`

Пример:

```env
SYNAPSE_BASE_URL=http://127.0.0.1:8008
```

Назначение:

- базовый URL для Matrix Client API.

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

### `MATRIX_SERVICE_USER_ID`

Пример:

```env
MATRIX_SERVICE_USER_ID=@redactor:matrix.e1capital.ru
```

Назначение:

- MXID сервисного пользователя, от имени которого идут redaction events в strict mode.

### `MATRIX_ACCESS_TOKEN`

Пример:

```env
MATRIX_ACCESS_TOKEN=<secret>
```

Назначение:

- access token сервисного пользователя.

### `TTL_HOURS`

Пример:

```env
TTL_HOURS=24
```

Назначение:

- возраст события, после которого оно попадает под удаление.

## 3. Переменные расписания

### `CRON_SCHEDULE`

Пример:

```env
CRON_SCHEDULE=0 5 * * *
```

Назначение:

- расписание запуска встроенного scheduler-процесса внутри контейнера.

Оговорка:

- при таком расписании это именно daily sweep, а не точное удаление через 24 часа.

### `TZ`

Пример:

```env
TZ=Europe/Moscow
```

Назначение:

- таймзона для scheduler и логов.

## 4. Переменные безопасности и режимов

### `DRY_RUN`

Пример:

```env
DRY_RUN=true
```

Назначение:

- если `true`, приложение только считает и логирует кандидатов, но не отправляет redaction.

### `REDACTION_REASON`

Рекомендуемый пример:

```env
REDACTION_REASON=Expired by policy
```

Назначение:

- текст, который будет записываться в redaction event.

Примечание:

- имя переменной лучше использовать как `REDACTION_REASON`, а не смешанный вариант. В коде следует поддерживать только одно каноническое имя.

### `ROOM_ACCESS_MODE`

Рекомендуемые значения:

- `strict_bot`
- `local_admin_fallback`

Назначение:

- явный выбор режима работы исполнителя.

## 5. Переменные производительности

### `BATCH_SIZE`

Пример:

```env
BATCH_SIZE=200
```

Назначение:

- размер одной DB-выборки и одной порции выполнения.

### `REQUEST_TIMEOUT_SECONDS`

Пример:

```env
REQUEST_TIMEOUT_SECONDS=15
```

Назначение:

- timeout на один HTTP-запрос к `Synapse`.

### `MAX_RETRIES`

Пример:

```env
MAX_RETRIES=3
```

Назначение:

- количество повторных попыток для retryable ошибок.

### `RATE_LIMIT_SLEEP_MS`

Пример:

```env
RATE_LIMIT_SLEEP_MS=200
```

Назначение:

- искусственное замедление между redaction requests, если понадобится бережный режим.

## 6. Переменные логирования и состояния

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

Назначение:

- локальная БД приложения для журналов запусков и ошибок.

### `LOCK_FILE_PATH`

Пример:

```env
LOCK_FILE_PATH=/app/var/run.lock
```

Назначение:

- защита от overlap.

## 7. Переменные отбора событий

### `EVENT_TYPE_ALLOWLIST`

Пример:

```env
EVENT_TYPE_ALLOWLIST=m.room.encrypted,m.room.message,m.reaction
```

Назначение:

- определяет, какие типы событий считаются “сообщениями” для redaction.

Почему нужна именно allowlist:

- это безопаснее, чем безусловный redaction всех non-state events.

## 8. Рекомендуемый `.env.example`

```env
SYNAPSE_BASE_URL=http://127.0.0.1:8008
SYNAPSE_DB_URL=sqlite+pysqlite:////opt/synapse/homeserver.db
MATRIX_SERVICE_USER_ID=@redactor:matrix.e1capital.ru
MATRIX_ACCESS_TOKEN=<secret>
TTL_HOURS=24
CRON_SCHEDULE=0 5 * * *
TZ=Europe/Moscow
DRY_RUN=true
REDACTION_REASON=Expired by policy
ROOM_ACCESS_MODE=strict_bot
BATCH_SIZE=200
REQUEST_TIMEOUT_SECONDS=15
MAX_RETRIES=3
RATE_LIMIT_SLEEP_MS=200
LOG_LEVEL=INFO
APP_STATE_DB_URL=sqlite+pysqlite:////app/var/state.db
LOCK_FILE_PATH=/app/var/run.lock
EVENT_TYPE_ALLOWLIST=m.room.encrypted,m.room.message,m.reaction
```

## 9. Валидируемые инварианты

Будущее приложение должно падать на старте, если:

- `SYNAPSE_BASE_URL` пустой;
- `SYNAPSE_DB_URL` пустой;
- `MATRIX_ACCESS_TOKEN` пустой в strict mode;
- `TTL_HOURS <= 0`;
- `BATCH_SIZE <= 0`;
- `CRON_SCHEDULE` синтаксически невалиден;
- `EVENT_TYPE_ALLOWLIST` пуст.
