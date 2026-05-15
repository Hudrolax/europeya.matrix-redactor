# Runtime и docker-compose

## 1. Базовый принцип

Приложение запускается внутри Docker-контейнера и управляется через `docker-compose`.

Важно:

- `docker-compose.yml` в репозитории предназначен для локального/test runtime и как шаблон;
- production compose для конкретного сервера должен храниться вне репозитория;
- это позволяет адаптировать пути, mount'ы, `network_mode`, `.env` и другие server-specific параметры без изменения общего проекта.

Рекомендуемая схема:

- один image;
- один long-running scheduler service;
- one-shot path через `docker compose run --rm`;
- отдельный writable volume под локальное состояние;
- явное перечисление runtime-переменных в `environment`;
- read-only mount каталога данных `Synapse`.
- read-only mount файла `.env` внутрь контейнера, чтобы изменения конфига применялись через обычный restart.

## 2. Почему scheduler внутри контейнера

Так проще сохранить переносимость runtime:

- нет привязки к host cron;
- один и тот же image обслуживает и плановые, и ручные запуски;
- compose остаётся единой точкой управления.

## 3. Generic compose-структура

### Service `matrix-redactor`

Отвечает за:

- рендер `crontab`;
- запуск `supercronic`;
- вызов `run-once` по расписанию;
- healthcheck.

### Manual path

Используется для:

- `dry-run-report`
- `run-once --dry-run`
- `run-once --real-run`
- `healthcheck`

## 4. Что должно быть смонтировано

### Для SQLite

```yaml
volumes:
  - ${SYNAPSE_DATA_DIR:-./synapse-data}:/opt/synapse:ro
  - ./var:/app/var
```

Причина:

- SQLite может использовать sidecar-файлы;
- каталожный mount безопаснее, чем mount одного файла.

### Для PostgreSQL

Каталог с SQLite не нужен.

Достаточно:

- сетевого доступа к PostgreSQL;
- корректного `SYNAPSE_DB_URL`;
- writable volume под `./var`.

## 5. Рекомендуемый compose-фрагмент

```yaml
services:
  matrix-redactor:
    build: .
    restart: unless-stopped
    environment:
      SYNAPSE_BASE_URL: "${SYNAPSE_BASE_URL}"
      SYNAPSE_DB_URL: "${SYNAPSE_DB_URL}"
      TTL_HOURS: "${TTL_HOURS:-24}"
      CRON_SCHEDULE: "${CRON_SCHEDULE:-0 5 * * *}"
      TZ: "${TZ:-UTC}"
      DRY_RUN: "${DRY_RUN:-false}"
      REDACTION_REASON: "${REDACTION_REASON:-Expired by policy}"
      BATCH_SIZE: "${BATCH_SIZE:-200}"
      MAX_CONCURRENT_SENDERS: "${MAX_CONCURRENT_SENDERS:-8}"
      REQUEST_TIMEOUT_SECONDS: "${REQUEST_TIMEOUT_SECONDS:-15}"
      MAX_RETRIES: "${MAX_RETRIES:-3}"
      RATE_LIMIT_SLEEP_MS: "${RATE_LIMIT_SLEEP_MS:-0}"
      LOG_LEVEL: "${LOG_LEVEL:-INFO}"
      APP_STATE_DB_URL: "${APP_STATE_DB_URL:-sqlite+pysqlite:////app/var/state.db}"
      LOCK_FILE_PATH: "${LOCK_FILE_PATH:-/app/var/run.lock}"
      EVENT_TYPE_ALLOWLIST: "${EVENT_TYPE_ALLOWLIST:-m.room.encrypted,m.room.message,m.reaction}"
      ROOM_ID_EXCLUDELIST: "${ROOM_ID_EXCLUDELIST:-}"
    volumes:
      - ./.env:/app/.env:ro
      - ${SYNAPSE_DATA_DIR:-./synapse-data}:/opt/synapse:ro
      - ./var:/app/var
    command:
      - /bin/sh
      - -lc
      - >
        python -m europeya_matrix_redactor.cli --env-file /app/.env render-crontab
        --output /app/var/crontab
        --command "python -m europeya_matrix_redactor.cli --env-file /app/.env run-once"
        && exec supercronic /app/var/crontab
    healthcheck:
      test: ["CMD", "python", "-m", "europeya_matrix_redactor.cli", "--env-file", "/app/.env", "healthcheck"]
      interval: 60s
      timeout: 10s
      retries: 3
```

Почему так:

- runtime-переменные явно видны в `docker compose config` и `docker inspect` через `environment`;
- `docker compose restart` не пересоздаёт контейнер и не перечитывает значения `environment`, сохранённые в момент create;
- bind-mount файла `.env` делает актуальный конфиг доступным внутри контейнера при каждом старте процесса;
- `render-crontab`, `run-once` и `healthcheck` читают один и тот же `/app/.env`;
- внутри приложения `.env` имеет приоритет над process environment, поэтому restart подхватывает свежий файл.

## 6. Loopback-only Synapse

Если `Synapse` слушает только `127.0.0.1` на host-машине, для контейнера может понадобиться отдельная сетевая схема, например:

- `network_mode: host`;
- или publish/reverse-proxy path;
- или bridge-сеть с доступным адресом `Synapse`.

Это зависит от окружения и не является частью бизнес-логики приложения.

## 7. Команды, которые должен поддерживать runtime

### Build

```bash
docker compose build
```

### Плановый запуск

```bash
docker compose up -d
```

### Применить изменения в `.env`

```bash
docker compose restart matrix-redactor
```

Этого достаточно, если менялись `TTL_HOURS`, `CRON_SCHEDULE` и другие runtime-параметры.
Если менялись compose-структурные вещи вроде `SYNAPSE_DATA_DIR`, нужен `docker compose up -d --force-recreate`.

### Dry-run

```bash
docker compose run --rm \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli --env-file /app/.env run-once --dry-run
```

### Real-run

```bash
docker compose run --rm \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli --env-file /app/.env run-once --real-run
```

### Healthcheck

```bash
docker compose run --rm \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli --env-file /app/.env healthcheck
```

## 8. Volume под локальное состояние

`./var:/app/var` должен содержать:

- локальную `state.db`;
- lock file;
- временные runtime-артефакты вроде сгенерированного `crontab`.

## 9. Поведение scheduler

Scheduler не содержит отдельной бизнес-логики.

Его задача:

- по cron запускать `run-once`;
- писать stdout/stderr в контейнерные логи;
- завершать дочерний процесс после выполнения.
