# Текущая структура реализации

Файл сохранён под историческим именем, но описывает текущую структуру кода, а не будущий план.

## 1. Структура репозитория

```text
europeya.matrix-redactor/
├── AGENTS.md
├── README.md
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
│       ├── dto.py
│       ├── locks.py
│       ├── logging.py
│       ├── scheduler.py
│       ├── clients/
│       │   └── matrix_client.py
│       ├── db/
│       │   ├── app_state_schema.py
│       │   ├── engine.py
│       │   ├── repositories.py
│       │   └── synapse_schema.py
│       └── services/
│           ├── executor.py
│           ├── planner.py
│           ├── room_access.py
│           └── run_journal.py
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_executor.py
    ├── test_repositories.py
    └── test_room_access.py
```

## 2. Основные точки входа

### `cli.py`

Поддерживает команды:

- `run-once`
- `dry-run-report`
- `healthcheck`
- `render-crontab`

### `config.py`

Содержит typed-конфиг приложения и валидацию `.env`.

### `clients/matrix_client.py`

Инкапсулирует Matrix HTTP API:

- `healthcheck`
- `redact_event`
- retry policy

## 3. Read-only DB слой

### `db/synapse_schema.py`

Описывает используемые таблицы `Synapse`, включая:

- `events`
- `redactions`
- `users`
- `access_tokens`
- `user_ips`
- `current_state_events`
- `room_memberships`

### `db/repositories.py`

Содержит read-only методы для:

- выборки кандидатов;
- sender scope;
- token lookup;
- current room membership;
- записи run journal в локальную state DB.

## 4. Сервисный слой

### `services/planner.py`

Считает cutoff и формирует dry-run summary.

### `services/room_access.py`

Проверяет:

- локальность пользователя;
- состояние `deactivated`;
- наличие токена;
- текущий membership в комнате.

### `services/executor.py`

Исполняет batch redaction и различает:

- skipped по sender scope;
- skipped по room membership;
- retryable/permanent HTTP failures.

### `services/run_journal.py`

Фиксирует lifecycle запуска в локальной state DB.

## 5. Текущая модель данных в DTO

### `CandidateEvent`

- `event_id`
- `room_id`
- `sender`
- `origin_server_ts`
- `event_type`

### `SenderScopeStatus`

- `user_id`
- `is_local`
- `is_active`
- `has_access_token`
- `mode`
- `failure_reason`

### `RedactionResult`

- `event_id`
- `room_id`
- `sender`
- `success`
- `retryable`
- `failure_kind`
- `http_status`
- `error_message`
- `redaction_event_id`

## 6. Что именно реализовано в репозитории

- read-only интеграция с `Synapse DB`;
- local-user access-token redaction path;
- preflight skip для пользователей вне комнаты;
- dry-run summary;
- run journal;
- Docker runtime со scheduler;
- unit и repository tests для ключевых сценариев.
