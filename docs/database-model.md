# Модель данных и SQLAlchemy-слой

## 1. Принцип

`Synapse DB` в этом проекте является только read-side источником данных.

Приложение:

- читает таблицы `Synapse`;
- не изменяет таблицы `Synapse`;
- выполняет write-side действия только через Matrix API.

## 2. Почему SQLAlchemy Core

Для проекта подходит `SQLAlchemy Core`, потому что нужен переносимый read-only query layer:

- без heavy ORM lifecycle;
- с явными join и батчевыми select;
- с одинаковой логикой для SQLite и PostgreSQL.

## 3. Таблицы, используемые текущей реализацией

### `events`

Источник кандидатных сообщений.

Ключевые поля:

- `event_id`
- `room_id`
- `type`
- `sender`
- `origin_server_ts`
- `outlier`
- `rejection_reason`
- `state_key`

### `redactions`

Используется для исключения уже обработанных событий.

Ключевое поле:

- `redacts`

### `users`

Используется для sender scope:

- локальный ли пользователь;
- деактивирован ли он.

### `access_tokens`

Используется для получения существующих access token локальных пользователей.

Ключевые поля:

- `user_id`
- `token`
- `valid_until_ms`
- `puppets_user_id`
- `last_validated`

### `user_ips`

Нужна для выбора наиболее актуального токена по `last_seen`.

Ключевые поля:

- `user_id`
- `access_token`
- `last_seen`

### `current_state_events`

Используется для проверки текущего membership пользователя в комнате.

### `room_memberships`

Используется вместе с `current_state_events`, чтобы определить, имеет ли пользователь `join` membership на момент redaction.

## 4. Базовый запрос кандидатов

Логический контракт:

```sql
SELECT
  e.event_id,
  e.room_id,
  e.sender,
  e.origin_server_ts,
  e.type
FROM events e
LEFT JOIN redactions r
  ON r.redacts = e.event_id
WHERE e.origin_server_ts < :cutoff_ms
  AND e.outlier = 0
  AND e.rejection_reason IS NULL
  AND e.state_key IS NULL
  AND e.type IN (:allowlist)
  AND r.redacts IS NULL
ORDER BY e.origin_server_ts ASC
LIMIT :batch_size;
```

## 5. Запрос sender scope

Приложению нужно для каждого отправителя знать:

- присутствует ли он в `users`;
- деактивирован ли;
- есть ли у него валидный токен.

Практически это означает:

- lookup в `users`;
- lookup в `access_tokens`;
- optional ranking токенов через `user_ips.last_seen`.

## 6. Запрос текущего membership

До HTTP redaction приложение должно проверить, что пользователь всё ещё состоит в комнате.

Логический контракт:

```sql
SELECT
  cse.state_key AS user_id,
  cse.room_id
FROM current_state_events cse
JOIN room_memberships rm
  ON rm.event_id = cse.event_id
WHERE cse.type = 'm.room.member'
  AND rm.membership = 'join'
  AND (cse.state_key, cse.room_id) IN (:sender_room_pairs);
```

Если пары `sender + room_id` нет в результате, redaction по такому событию не должен выполняться.

## 7. Why allowlist

Allowlist по умолчанию:

- `m.room.encrypted`
- `m.room.message`
- `m.reaction`

Это безопаснее, чем redaction всех non-state событий, потому что:

- снижает риск затронуть служебные типы;
- делает поведение конфигурируемым;
- упрощает dry-run интерпретацию.

## 8. Индексы и практические ожидания

Для нормальной работы желательно, чтобы база имела индексы как минимум на:

- `events(origin_server_ts)`
- `redactions(redacts)`

Membership-проверка также выигрывает от индексов текущего state и membership таблиц, но проект не зависит от конкретных имен индексов.

## 9. SQLite-особенности

Для SQLite желательно монтировать каталог БД целиком, а не только один файл, потому что возможны sidecar-файлы:

- `*.db-wal`
- `*.db-shm`

В контейнере приложение работает только с логическим DSN, например:

- `sqlite+pysqlite:////opt/synapse/homeserver.db`

## 10. Контракт репозитория

`SynapseEventRepository` должен уметь:

- `count_candidates(...)`
- `count_candidates_by_type(...)`
- `count_candidates_by_room(...)`
- `count_candidates_by_sender(...)`
- `sample_candidates(...)`
- `iter_candidates(...)`
- `get_sender_profiles(...)`
- `get_sender_tokens(...)`
- `get_joined_room_memberships(...)`

## 11. Что нельзя делать в SQLAlchemy-слое

- не писать в таблицы `Synapse`;
- не удалять события через SQL;
- не полагаться на расшифровку `m.room.encrypted`;
- не смешивать read-side `Synapse` schema с local state schema приложения.
