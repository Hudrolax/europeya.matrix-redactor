from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    Column,
)

app_state_metadata = MetaData()

runs = Table(
    "runs",
    app_state_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("run_mode", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("cutoff_ms", Integer, nullable=False),
    Column("candidate_count", Integer, nullable=False, default=0),
    Column("processed_count", Integer, nullable=False, default=0),
    Column("successful_redactions", Integer, nullable=False, default=0),
    Column("skipped_count", Integer, nullable=False, default=0),
    Column("failure_count", Integer, nullable=False, default=0),
    Column("summary_json", JSON),
    Column("error_message", Text),
)

run_failures = Table(
    "run_failures",
    app_state_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("failure_kind", Text, nullable=False),
    Column("event_id", Text),
    Column("room_id", Text),
    Column("retryable", Boolean, nullable=False, default=False),
    Column("http_status", Integer),
    Column("error_message", Text),
)
