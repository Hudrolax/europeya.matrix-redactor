# AGENTS.md

Перед началом любой реализации или доработки по этому проекту сначала прочитайте основную документацию:

- [docs/README.md](/Users/hudro/code/europeya.matrix-redactor/docs/README.md)

Ключевые проектные документы:

- [architecture.md](/Users/hudro/code/europeya.matrix-redactor/docs/architecture.md)
- [database-model.md](/Users/hudro/code/europeya.matrix-redactor/docs/database-model.md)
- [runtime-compose.md](/Users/hudro/code/europeya.matrix-redactor/docs/runtime-compose.md)
- [configuration-reference.md](/Users/hudro/code/europeya.matrix-redactor/docs/configuration-reference.md)
- [room-access-and-permissions.md](/Users/hudro/code/europeya.matrix-redactor/docs/room-access-and-permissions.md)
- [testing.md](/Users/hudro/code/europeya.matrix-redactor/docs/testing.md)
- [implementation-plan.md](/Users/hudro/code/europeya.matrix-redactor/docs/implementation-plan.md)
- [decision-log.md](/Users/hudro/code/europeya.matrix-redactor/docs/decision-log.md)

Минимальные правила для следующих проходов:

- не писать напрямую в БД `Synapse`;
- считать `Synapse DB` только read-only источником;
- для исчезновения сообщений у клиентов использовать redaction-подход;
- учитывать, что ежедневный запуск в `05:00` даёт daily sweep, а не точный TTL ровно 24 часа;
- не игнорировать ограничение по room permissions: strict federated mode требует сервисного пользователя с правом `redact` в комнатах.
