# europeya.matrix-redactor

Документация текущей реализации проекта для server-side удаления Matrix-сообщений через `m.room.redaction`.

## Цель

Приложение должно:

- читать `Synapse DB` только в read-only режиме;
- находить сообщения старше заданного TTL;
- удалять их штатным Matrix-механизмом `redaction`;
- выполнять обработку по расписанию или в one-shot режиме;
- сохранять локальный журнал запусков и ошибок.

## Текущая архитектура

Проект реализован в модели `local_user_access_token`.

Это означает:

- кандидатные события выбираются из `Synapse DB`;
- поддерживаются только локальные пользователи homeserver;
- для redaction используются уже существующие access token этих пользователей из `Synapse DB`;
- перед redaction приложение проверяет, что пользователь активен, имеет валидный token и всё ещё состоит в комнате;
- если пользователь уже покинул комнату, событие пропускается до HTTP-запроса;
- запись в `Synapse DB` не выполняется ни при каких сценариях.

## Ограничения

- события remote/federated отправителей не поддерживаются этой архитектурой;
- локальный пользователь без валидного access token пропускается;
- локальный пользователь, который уже не состоит в комнате, пропускается;
- расписание вида `раз в сутки` даёт daily sweep, а не точный TTL ровно через 24 часа.

## Что входит в scope

- read-only SQLAlchemy-слой для `Synapse DB`;
- dry-run и real-run режимы;
- batched redaction через Matrix Client API;
- preflight-проверка sender scope и текущего membership;
- локальный run journal;
- Docker runtime со scheduler внутри контейнера.

## Что не входит в scope

- прямое изменение таблиц `Synapse`;
- восстановление уже отредактированных сообщений;
- поддержка remote/federated отправителей в текущей архитектуре;
- получение новых токенов через admin API;
- расшифровка `m.room.encrypted`;
- управление комнатами, power levels и членством пользователей.

## Структура документации

- [docs/architecture.md](/Users/hudro/code/europeya.matrix-redactor/docs/architecture.md) — поток выполнения и ключевые компоненты.
- [docs/database-model.md](/Users/hudro/code/europeya.matrix-redactor/docs/database-model.md) — используемые таблицы и read-only запросы.
- [docs/runtime-compose.md](/Users/hudro/code/europeya.matrix-redactor/docs/runtime-compose.md) — контейнерный runtime без привязки к конкретной среде.
- [docs/configuration-reference.md](/Users/hudro/code/europeya.matrix-redactor/docs/configuration-reference.md) — актуальные переменные окружения.
- [docs/room-access-and-permissions.md](/Users/hudro/code/europeya.matrix-redactor/docs/room-access-and-permissions.md) — ограничения текущей модели доступа.
- [docs/testing.md](/Users/hudro/code/europeya.matrix-redactor/docs/testing.md) — стратегия тестирования и smoke-checks.
- [docs/implementation-plan.md](/Users/hudro/code/europeya.matrix-redactor/docs/implementation-plan.md) — текущая структура кода и модулей.
- [docs/decision-log.md](/Users/hudro/code/europeya.matrix-redactor/docs/decision-log.md) — принятые архитектурные решения.

## Источники

- [Matrix Client-Server API: redact](https://spec.matrix.org/latest/client-server-api/index.html#put_matrixclientv3roomsroomidredacteventidtxnid)
- [Synapse Message Retention Policies](https://element-hq.github.io/synapse/latest/message_retention_policies.html)
