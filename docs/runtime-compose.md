# Runtime и docker-compose

## 1. Базовый принцип

Приложение должно запускаться внутри Docker-контейнера и управляться через `docker-compose`.

Рекомендуемая схема:

- один image;
- один основной сервис scheduler;
- один дополнительный manual run path для `run-once`;
- один volume для локального состояния приложения;
- read-only mount каталога с SQLite БД `Synapse`.

## 2. Почему scheduler внутри контейнера

Пользовательское требование прямо просит запуск “внутри docker контейнера через docker-compose раз в сутки”.

Наиболее прагматичная модель:

- внутри контейнера работает `supercronic`;
- он по cron запускает Python CLI-команду `run-once`;
- та же команда используется вручную для dry-run и аварийных запусков.

Плюсы:

- нет зависимости от host cron;
- одинаковый код для планового и ручного запуска;
- проще эксплуатация и перенос между серверами.

## 3. Рекомендуемая структура compose

### Service `matrix-redactor`

Назначение:

- long-running scheduler container.

Ответственность:

- ждать нужное время;
- запускать one-shot команду;
- отдавать stdout/stderr в Docker logs.

### Manual execution path

Нужен для:

- dry-run;
- smoke test;
- ручного аварийного запуска после исправления прав доступа.

Это может быть:

- отдельный compose profile;
- или `docker compose run --rm matrix-redactor ...`.

## 4. Что должно быть смонтировано

### Для SQLite

Нужно монтировать не только файл, а весь каталог:

```yaml
volumes:
  - /srv/matrix/synapse:/opt/synapse:ro
  - ./var:/app/var
```

Причина:

- у SQLite могут существовать `homeserver.db-wal` и `homeserver.db-shm`;
- mount только одного файла может дать несогласованное чтение.

### Для будущего PostgreSQL

Каталог БД больше не нужен.

Останется только:

- сетевой доступ к PostgreSQL;
- `SYNAPSE_DB_URL` в `.env`;
- volume под локальное состояние приложения.

## 5. Рекомендуемый compose-фрагмент

Это проектная спецификация, а не финальный боевой файл:

```yaml
services:
  matrix-redactor:
    build: .
    container_name: matrix-redactor
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - /srv/matrix/synapse:/opt/synapse:ro
      - ./var:/app/var
    command: ["supercronic", "/app/crontab"]
    healthcheck:
      test: ["CMD", "python", "-m", "europeya_matrix_redactor.cli", "healthcheck"]
      interval: 60s
      timeout: 10s
      retries: 3
```

## 6. Что должно быть в образе

В будущем `Dockerfile` должен содержать:

- Python runtime;
- зависимости проекта;
- `supercronic`;
- CLI entrypoint;
- каталог `/app/var` под state DB и lock file.

Рекомендуемая база:

- `python:3.13-slim`

## 7. Команды эксплуатации, которые должны поддерживаться

### Build

```bash
docker compose build
```

### Плановый запуск через scheduler

```bash
docker compose up -d
```

### Dry-run вручную

```bash
docker compose run --rm \
  -e DRY_RUN=true \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli run-once
```

### Реальный one-shot запуск

```bash
docker compose run --rm \
  -e DRY_RUN=false \
  matrix-redactor \
  python -m europeya_matrix_redactor.cli run-once
```

### Просмотр логов

```bash
docker compose logs -f matrix-redactor
```

## 8. Таймзона

Для scheduler надо явно фиксировать timezone.

Рекомендуемый вариант:

- `TZ=Europe/Moscow`

Это важно, чтобы `05:00` в конфиге всегда соответствовал ожидаемому локальному времени сервера/команды.

## 9. Поведение scheduler

Scheduler не должен содержать отдельную бизнес-логику.

Его задача:

- по cron вызывать `run-once`;
- завершать дочерний процесс;
- писать его stdout/stderr в общий log stream.

Вся логика redaction должна жить только в Python CLI.

## 10. Volume под состояние приложения

Нужен отдельный writable volume:

- `./var:/app/var`

Там должны храниться:

- `state.db` или аналогичный локальный журнал;
- lock file;
- при необходимости JSON-отчёты dry-run.

## 11. Обязательные эксплуатационные проверки

После первого запуска будущего контейнера надо уметь проверить:

- контейнер поднялся;
- scheduler действительно ждёт и не падает в restart loop;
- `healthcheck` проходит;
- `run-once --dry-run` видит боевую БД;
- при реальном запуске redaction доходят до `Synapse`.

## 12. Отдельная оговорка про суточное расписание

Если `.env` содержит cron на `05:00` один раз в сутки, это означает:

- sweep выполняется один раз в день;
- точность фактического TTL не 24 часа, а “на ближайшем ежедневном запуске после достижения 24 часов”.

Это не баг и не пограничный случай, а фундаментальное свойство такого расписания.
