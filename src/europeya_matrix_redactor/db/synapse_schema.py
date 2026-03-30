from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, MetaData, Table, Text, Column

synapse_metadata = MetaData()

events = Table(
    "events",
    synapse_metadata,
    Column("stream_ordering", Integer, primary_key=True),
    Column("event_id", Text, nullable=False, unique=True),
    Column("type", Text, nullable=False),
    Column("room_id", Text, nullable=False),
    Column("origin_server_ts", BigInteger, nullable=False),
    Column("sender", Text, nullable=False),
    Column("outlier", Boolean, nullable=False, default=False),
    Column("state_key", Text),
    Column("rejection_reason", Text),
)

redactions = Table(
    "redactions",
    synapse_metadata,
    Column("event_id", Text, nullable=False),
    Column("redacts", Text, nullable=False),
    Column("have_censored", Boolean, nullable=False, default=False),
    Column("received_ts", BigInteger),
)

event_json = Table(
    "event_json",
    synapse_metadata,
    Column("event_id", Text, primary_key=True),
    Column("json", Text, nullable=False),
)

current_state_events = Table(
    "current_state_events",
    synapse_metadata,
    Column("room_id", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("state_key", Text, nullable=False),
    Column("event_id", Text, nullable=False),
)

room_memberships = Table(
    "room_memberships",
    synapse_metadata,
    Column("event_id", Text, primary_key=True),
    Column("room_id", Text, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("membership", Text, nullable=False),
)

users = Table(
    "users",
    synapse_metadata,
    Column("name", Text, primary_key=True),
    Column("is_guest", Boolean, nullable=False, default=False),
    Column("admin", Boolean, nullable=False, default=False),
    Column("deactivated", Boolean, nullable=False, default=False),
)
