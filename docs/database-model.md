# Модель данных и SQLAlchemy-слой

## 1. Принцип

`Synapse DB` в этом проекте является только read-side источником данных.

Это означает:

- приложение читает таблицы `Synapse`;
- приложение не изменяет таблицы `Synapse`;
- удаление сообщений выполняется через Matrix API, а не SQL `DELETE`.

## 2. Почему SQLAlchemy Core

Для этого проекта лучше подходит `SQLAlchemy Core`, а не “толстый ORM”.

Причины:

- запросы простые, но чувствительные к диалекту;
- нужен перенос между SQLite и PostgreSQL;
- read-only таблицы `Synapse` не требуют ORM lifecycle;
- Core удобен для батчевых селектов и явных join.

ORM допускается только для локальной БД самого приложения, если это упростит журнал запусков.

## 3. Таблицы Synapse, которые нужны в первом релизе

### `events`

Главная таблица для первичной выборки.

Нас интересуют поля:

- `event_id`
- `room_id`
- `type`
- `sender`
- `origin_server_ts`
- `outlier`
- `rejection_reason`
- `state_key`

Фактическая схема на сервере:

- `stream_ordering INTEGER PRIMARY KEY`
- `event_id TEXT UNIQUE`
- `type TEXT`
- `room_id TEXT`
- `origin_server_ts BIGINT`
- `sender TEXT`
- `outlier BOOL`
- `state_key TEXT`
- `rejection_reason TEXT`

### `redactions`

Нужна для исключения уже обработанных событий.

Критичное поле:

- `redacts`

Фактическая схема на сервере:

- `event_id TEXT`
- `redacts TEXT`
- `have_censored BOOL`
- `received_ts BIGINT`

### `event_json`

Нужна как вспомогательная таблица.

Первый релиз может использовать её минимально, но она понадобится:

- для room state inspection;
- для анализа `m.room.power_levels`;
- для будущих расширений логики отбора.

### `current_state_events`

Нужна для анализа текущего состояния комнаты.

Возможные применения:

- проверить membership сервисного пользователя;
- получить ссылки на актуальные state events;
- определить наличие `m.room.power_levels`.

### `room_memberships`

Нужна как вспомогательный read-only источник по membership history.

Полезна для:

- отладки;
- аналитики проблемных комнат;
- будущих расширений preflight-логики.

### `users`

Не нужна для строгого bot-mode, но нужна:

- для local-only fallback mode;
- для административной аналитики;
- для preflight отчёта по локальным пользователям.

## 4. Базовый запрос кандидатов

Логический запрос:

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

Это не приложение и не готовый код, а контракт запроса, который затем будет выражен через SQLAlchemy Core.

## 5. Что реально известно по индексам на боевой БД

На сервере `45.134.27.106` найдены такие индексы:

- `events_ts` на `events(origin_server_ts)`
- `redactions_redacts` на `redactions(redacts)`
- несколько служебных индексов на membership/state таблицах

План реального запроса показал:

- поиск по `events` идёт через `events_ts`;
- join на `redactions` идёт через `redactions_redacts`.

Практический вывод:

- правило отбора по `origin_server_ts` пригодно для production;
- batched scan можно строить именно от временного cutoff;
- отдельный локальный checkpoint по `stream_ordering` не обязателен в первом релизе.

## 6. Набор event type по умолчанию

Безопасный allowlist для первого релиза:

- `m.room.encrypted`
- `m.room.message`
- `m.reaction`

Почему не брать “все события с `state_key IS NULL`”:

- туда могут попасть служебные события, которые пользователь не воспринимает как сообщения;
- для первого релиза нужен консервативный набор;
- расширение списка должно быть конфигурационным.

На текущем сервере почти весь пользовательский поток уже покрывается этим allowlist.

## 7. Как выражать это через SQLAlchemy

Рекомендуемая структура read-side слоя:

- `SynapseEventRepository`
- `RoomStateRepository`
- `SynapseDialectFactory`

### `SynapseEventRepository`

Отвечает за:

- выборку батча кандидатов;
- count кандидатов для dry-run summary;
- выборку по room/user/time при отладке.

### `RoomStateRepository`

Отвечает за:

- получение текущих membership state;
- получение `m.room.power_levels`;
- проверку room capability для сервисного пользователя.

### `SynapseDialectFactory`

Отвечает за:

- создание engine/session;
- одинаковую настройку SQLite и PostgreSQL;
- read-only connect options.

## 8. SQLite-особенности

Для SQLite в compose нужно учитывать не только `homeserver.db`, но и возможные sidecar-файлы:

- `homeserver.db-wal`
- `homeserver.db-shm`

Поэтому лучше монтировать каталог БД целиком read-only:

- `/srv/matrix/synapse:/opt/synapse:ro`

А уже внутри контейнера использовать:

- `sqlite+pysqlite:////opt/synapse/homeserver.db`

## 9. PostgreSQL-особенности

При переходе на PostgreSQL меняться должны только:

- DSN;
- драйвер;
- возможно, таймауты и pool settings.

Бизнес-логика не должна зависеть от:

- sqlite-specific pragma;
- `rowid`;
- локальных путей;
- ручного парсинга JSON через SQLite-функции.

## 10. Локальная БД приложения

Отдельно от `Synapse DB` допустимо держать internal state DB.

Она нужна для:

- run journal;
- сведений о неудачных redaction;
- lock state;
- аудита.

Рекомендуемая технология:

- ещё одна SQLite БД приложения под SQLAlchemy.

Это нормально, потому что:

- она не вмешивается в `Synapse`;
- её schema контролирует само приложение.

## 11. Контракт репозиториев для будущей реализации

Минимальный интерфейс:

- `count_candidates(cutoff_ms, allowlist) -> int`
- `iter_candidates(cutoff_ms, allowlist, batch_size) -> Iterator[list[CandidateEvent]]`
- `get_room_access_snapshot(room_ids, service_user_id) -> dict`
- `get_power_levels(room_ids) -> dict`

Минимальный DTO `CandidateEvent`:

- `event_id`
- `room_id`
- `sender`
- `origin_server_ts`
- `event_type`

## 12. Что нельзя делать в SQLAlchemy-слое

- не redaction'ить события напрямую через SQL;
- не записывать что-либо в таблицы `Synapse`;
- не завязываться на текущее содержимое `event_json` для E2EE message body;
- не полагаться на расшифровку `m.room.encrypted`.

Итог:

- SQLAlchemy-слой здесь нужен как переносимый read-only query layer;
- write-side логика находится только в HTTP client слое.

