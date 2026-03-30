from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url

from europeya_matrix_redactor.db.app_state_schema import app_state_metadata


def _create_sqlite_readonly_engine(database_path: str) -> Engine:
    resolved = str(Path(database_path).expanduser())

    def creator() -> sqlite3.Connection:
        return sqlite3.connect(
            f"file:{resolved}?mode=ro",
            uri=True,
            check_same_thread=False,
        )

    engine = create_engine("sqlite+pysqlite://", creator=creator, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _enable_query_only(dbapi_connection: sqlite3.Connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA query_only = ON")
        finally:
            cursor.close()

    return engine


def build_synapse_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if not url.database:
            raise ValueError("SQLite SYNAPSE_DB_URL must include a database path")
        return _create_sqlite_readonly_engine(url.database)

    engine = create_engine(database_url, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_readonly(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        finally:
            cursor.close()

    return engine


def build_app_state_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def ensure_app_state_schema(engine: Engine) -> None:
    app_state_metadata.create_all(engine)


def ping_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
