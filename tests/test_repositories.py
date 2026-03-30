from __future__ import annotations

from sqlalchemy import create_engine

from europeya_matrix_redactor.db.engine import build_synapse_engine
from europeya_matrix_redactor.db.repositories import SynapseEventRepository
from europeya_matrix_redactor.db.synapse_schema import access_tokens, events, redactions, user_ips, users


def test_candidate_repository_filters_redacted_state_and_recent_events(
    make_synapse_db,
) -> None:
    db_path = make_synapse_db()
    writer = create_engine(f"sqlite+pysqlite:///{db_path}")
    with writer.begin() as connection:
        connection.execute(
            events.insert(),
            [
                {
                    "stream_ordering": 1,
                    "event_id": "$old-encrypted",
                    "type": "m.room.encrypted",
                    "room_id": "!room-a:example.com",
                    "origin_server_ts": 100,
                    "sender": "@alice:example.com",
                    "outlier": False,
                    "state_key": None,
                    "rejection_reason": None,
                },
                {
                    "stream_ordering": 2,
                    "event_id": "$old-message",
                    "type": "m.room.message",
                    "room_id": "!room-b:example.com",
                    "origin_server_ts": 200,
                    "sender": "@bob:example.com",
                    "outlier": False,
                    "state_key": None,
                    "rejection_reason": None,
                },
                {
                    "stream_ordering": 3,
                    "event_id": "$recent-message",
                    "type": "m.room.message",
                    "room_id": "!room-b:example.com",
                    "origin_server_ts": 2_000,
                    "sender": "@bob:example.com",
                    "outlier": False,
                    "state_key": None,
                    "rejection_reason": None,
                },
                {
                    "stream_ordering": 4,
                    "event_id": "$state-event",
                    "type": "m.room.member",
                    "room_id": "!room-b:example.com",
                    "origin_server_ts": 50,
                    "sender": "@bob:example.com",
                    "outlier": False,
                    "state_key": "@bob:example.com",
                    "rejection_reason": None,
                },
                {
                    "stream_ordering": 5,
                    "event_id": "$already-redacted",
                    "type": "m.room.message",
                    "room_id": "!room-a:example.com",
                    "origin_server_ts": 75,
                    "sender": "@alice:example.com",
                    "outlier": False,
                    "state_key": None,
                    "rejection_reason": None,
                },
            ],
        )
        connection.execute(
            redactions.insert(),
            [
                {
                    "event_id": "$redaction",
                    "redacts": "$already-redacted",
                    "have_censored": True,
                    "received_ts": 500,
                },
            ],
        )
        connection.execute(
            users.insert(),
            [
                {"name": "@alice:example.com", "is_guest": False, "admin": False, "deactivated": False},
                {"name": "@bob:example.com", "is_guest": False, "admin": False, "deactivated": True},
            ],
        )
        connection.execute(
            access_tokens.insert(),
            [
                {
                    "id": 1,
                    "user_id": "@alice:example.com",
                    "device_id": "ALICE_OLD",
                    "token": "alice-old",
                    "valid_until_ms": None,
                    "puppets_user_id": None,
                    "last_validated": 100,
                    "used": True,
                },
                {
                    "id": 2,
                    "user_id": "@alice:example.com",
                    "device_id": "ALICE_NEW",
                    "token": "alice-new",
                    "valid_until_ms": None,
                    "puppets_user_id": None,
                    "last_validated": 200,
                    "used": True,
                },
                {
                    "id": 3,
                    "user_id": "@bob:example.com",
                    "device_id": "BOB_EXPIRED",
                    "token": "bob-expired",
                    "valid_until_ms": 50,
                    "puppets_user_id": None,
                    "last_validated": 300,
                    "used": True,
                },
                {
                    "id": 4,
                    "user_id": "@bob:example.com",
                    "device_id": "BOB_ACTIVE",
                    "token": "bob-active",
                    "valid_until_ms": 5_000,
                    "puppets_user_id": None,
                    "last_validated": 400,
                    "used": True,
                },
                {
                    "id": 5,
                    "user_id": "@alice:example.com",
                    "device_id": "ALICE_PUPPET",
                    "token": "alice-puppet",
                    "valid_until_ms": None,
                    "puppets_user_id": "@bridge:example.com",
                    "last_validated": 500,
                    "used": True,
                },
            ],
        )
        connection.execute(
            user_ips.insert(),
            [
                {
                    "user_id": "@alice:example.com",
                    "access_token": "alice-old",
                    "device_id": "ALICE_OLD",
                    "ip": "127.0.0.1",
                    "user_agent": "Element/old",
                    "last_seen": 100,
                },
                {
                    "user_id": "@alice:example.com",
                    "access_token": "alice-new",
                    "device_id": "ALICE_NEW",
                    "ip": "127.0.0.2",
                    "user_agent": "Element/new",
                    "last_seen": 200,
                },
                {
                    "user_id": "@bob:example.com",
                    "access_token": "bob-active",
                    "device_id": "BOB_ACTIVE",
                    "ip": "127.0.0.3",
                    "user_agent": "Element/bob",
                    "last_seen": 300,
                },
            ],
        )
    writer.dispose()

    engine = build_synapse_engine(f"sqlite+pysqlite:///{db_path}")
    repository = SynapseEventRepository(engine)

    try:
        allowlist = ("m.room.encrypted", "m.room.message", "m.reaction")
        assert repository.count_candidates(1_000, allowlist) == 2
        assert repository.count_candidates_by_type(1_000, allowlist) == {
            "m.room.encrypted": 1,
            "m.room.message": 1,
        }
        assert repository.count_candidates_by_room(1_000, allowlist) == {
            "!room-a:example.com": 1,
            "!room-b:example.com": 1,
        }
        assert repository.count_candidates_by_sender(1_000, allowlist) == {
            "@alice:example.com": 1,
            "@bob:example.com": 1,
        }
        assert repository.get_sender_profiles(
            ["@alice:example.com", "@bob:example.com", "@remote:elsewhere"],
        ) == {
            "@alice:example.com": {"deactivated": False},
            "@bob:example.com": {"deactivated": True},
        }
        assert repository.get_sender_tokens(
            ["@alice:example.com", "@bob:example.com", "@remote:elsewhere"],
            now_ms=1_000,
        ) == {
            "@alice:example.com": ["alice-new", "alice-old"],
            "@bob:example.com": ["bob-active"],
        }

        batches = list(repository.iter_candidates(1_000, allowlist, batch_size=1))
        assert [[candidate.event_id for candidate in batch] for batch in batches] == [
            ["$old-encrypted"],
            ["$old-message"],
        ]
    finally:
        engine.dispose()
