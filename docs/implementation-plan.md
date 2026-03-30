# План реализации

Этот документ нужен, чтобы следующий проход мог сразу писать проект без дополнительного архитектурного ресёрча.

## 1. Рекомендуемая структура файлов

```text
europeya.matrix-redactor/
├── AGENTS.md
├── pyproject.toml
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── crontab
├── docs/
│   ├── README.md
│   ├── architecture.md
│   ├── configuration-reference.md
│   ├── database-model.md
│   ├── decision-log.md
│   ├── implementation-plan.md
│   ├── room-access-and-permissions.md
│   ├── runtime-compose.md
│   └── testing.md
├── src/
│   └── europeya_matrix_redactor/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── logging.py
│       ├── scheduler.py
│       ├── dto.py
│       ├── locks.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   ├── synapse_schema.py
│       │   ├── app_state_schema.py
│       │   └── repositories.py
│       ├── services/
│       │   ├── planner.py
│       │   ├── room_access.py
│       │   ├── executor.py
│       │   └── run_journal.py
│       └── clients/
│           ├── __init__.py
│           └── matrix_client.py
└── tests/
    ├── test_config.py
    ├── test_repositories.py
    ├── test_executor.py
    ├── test_room_access.py
    └── fixtures/
```

## 2. Ответственность модулей

### `cli.py`

Должен поддерживать команды:

- `run-once`
- `healthcheck`
- `dry-run-report`

### `config.py`

Должен:

- читать `.env`;
- валидировать значения;
- нормализовать allowlist;
- возвращать строго типизированный config object.

### `db/engine.py`

Должен:

- строить SQLAlchemy engine;
- настраивать read-only подключение к `Synapse DB`;
- поддерживать SQLite и PostgreSQL.

### `db/synapse_schema.py`

Должен описывать нужные таблицы:

- `events`
- `redactions`
- `event_json`
- `current_state_events`
- `room_memberships`
- `users`

### `db/app_state_schema.py`

Должен описывать локальные таблицы приложения:

- `runs`
- `run_failures`
- возможно, `room_preflight_failures`

### `db/repositories.py`

Должен содержать:

- `SynapseEventRepository`
- `RoomStateRepository`
- `RunJournalRepository`

### `services/planner.py`

Должен:

- считать `cutoff`;
- выбирать кандидатов батчами;
- выдавать execution plan;
- поддерживать dry-run summary.

### `services/room_access.py`

Должен:

- проверять доступ сервисного пользователя к комнате;
- при необходимости читать `m.room.power_levels`;
- возвращать структурированный статус комнаты.

### `services/executor.py`

Должен:

- вызывать Matrix redaction endpoint;
- делать retries для retryable ошибок;
- возвращать результаты по каждому `event_id`.

### `services/run_journal.py`

Должен:

- фиксировать старт запуска;
- писать summary;
- писать ошибки;
- обновлять итоговый статус run.

### `clients/matrix_client.py`

Должен:

- инкапсулировать HTTP-вызовы к `Synapse`;
- поддерживать redaction endpoint;
- уметь делать healthcheck.

## 3. Предлагаемая последовательность реализации

### Этап 1. Каркас проекта

- `pyproject.toml`
- package layout
- config loader
- logging
- CLI skeleton

### Этап 2. Read-only DB слой

- SQLAlchemy schema
- engine factory
- repository queries
- unit tests на fixture SQLite

### Этап 3. Matrix client

- healthcheck
- redaction call
- error mapping
- retry policy

### Этап 4. Planner и executor

- dry-run
- batch iteration
- room access verifier
- real-run execution

### Этап 5. Runtime

- Dockerfile
- crontab
- docker-compose
- healthcheck

### Этап 6. Acceptance

- dry-run на реальной БД
- тестовая комната
- federated room
- идемпотентность

## 4. Библиотеки, которые стоит рассмотреть

- `sqlalchemy`
- `pydantic-settings` или `pydantic`
- `httpx`
- `tenacity`
- `structlog` или стандартный `logging` с JSON formatter
- `pytest`

Для PostgreSQL:

- `psycopg`

## 5. Формат DTO и доменных сущностей

### `CandidateEvent`

Поля:

- `event_id`
- `room_id`
- `sender`
- `origin_server_ts`
- `event_type`

### `RoomAccessStatus`

Поля:

- `room_id`
- `membership_ok`
- `power_level_ok`
- `mode`
- `failure_reason`

### `RedactionResult`

Поля:

- `event_id`
- `room_id`
- `success`
- `retryable`
- `http_status`
- `error_message`
- `redaction_event_id`

## 6. Что должно быть реализовано в первом релизе обязательно

- strict bot mode;
- dry-run;
- one-shot run;
- scheduler run;
- local run journal;
- idempotent selection;
- batch processing;
- structured logs.

## 7. Что можно оставить на второй релиз

- local-only admin fallback mode;
- расширенный отчёт по комнатам;
- Prometheus metrics;
- экспорт отчёта в файл;
- конфигурируемые event type beyond default allowlist;
- отдельная preflight-команда.

## 8. Acceptance checklist для следующего прохода

Будущий код нельзя считать завершённым, пока не будут готовы:

- `README` обновлён под фактическую реализацию;
- `.env.example` совпадает с кодом;
- `docker-compose.yml` совпадает с runtime-моделью;
- есть тесты на SQLAlchemy-репозитории;
- есть dry-run и real-run;
- есть блокировка overlap;
- есть хотя бы один документированный сценарий ручного теста.
