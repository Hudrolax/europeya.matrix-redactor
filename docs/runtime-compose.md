# Runtime и docker-compose

## 1. Базовый принцип

Приложение запускается внутри Docker-контейнера и управляется через `docker-compose`.

Рекомендуемая схема:

- один image;
- один long-running scheduler service;
- one-shot path через `docker compose run --rm`;
- отдельный writable volume под локальное состояние;
- read-only mount каталога данных `Synapse`.

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
    env_file:
      - .env
    volumes:
      - ${SYNAPSE_DATA_DIR:-./synapse-data}:/opt/synapse:ro
      - ./var:/app/var
    command:
      - /bin/sh
      - -lc
      - python -m europeya_matrix_redactor.cli render-crontab --output /app/var/crontab && exec supercronic /app/var/crontab
    healthcheck:
      test: ["CMD", "python", "-m", "europeya_matrix_redactor.cli", "healthcheck"]
      interval: 60s
      timeout: 10s
      retries: 3
```

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

### Dry-run

```bash
docker compose run --rm \
  -e DRY_RUN=true \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli run-once
```

### Real-run

```bash
docker compose run --rm \
  -e DRY_RUN=false \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli run-once
```

### Healthcheck

```bash
docker compose run --rm \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli healthcheck
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
