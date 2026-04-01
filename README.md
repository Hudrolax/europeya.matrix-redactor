# europeya.matrix-redactor

Python-приложение для планового удаления Matrix-сообщений через `m.room.redaction` на основе read-only данных из `Synapse DB`.

Текущая архитектура проекта:

- читает кандидатов из `Synapse DB` без записи в неё;
- поддерживает только локальных пользователей;
- берёт существующие user access token из таблиц `Synapse`;
- распределяет redaction'ы между пользователями в sender-aware round-robin режиме;
- пропускает события, если пользователь деактивирован, не имеет валидного токена или уже не состоит в комнате;
- отправляет redaction только через Matrix Client API;
- хранит журнал запусков во внутренней локальной БД приложения.

Подробная документация находится в [docs/README.md](/Users/hudro/code/europeya.matrix-redactor/docs/README.md).
Локальные правила доступа к серверам и эксплуатационный контекст вынесены в [~/AGENTS.md](/Users/hudro/AGENTS.md).
