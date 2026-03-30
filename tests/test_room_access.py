from __future__ import annotations

from sqlalchemy import create_engine

from europeya_matrix_redactor.db.engine import build_synapse_engine
from europeya_matrix_redactor.db.repositories import SynapseEventRepository
from europeya_matrix_redactor.db.synapse_schema import users
from europeya_matrix_redactor.services.room_access import SenderScopeVerifier


def test_sender_scope_verifier_detects_local_remote_and_deactivated_users(make_synapse_db) -> None:
    db_path = make_synapse_db()
    writer = create_engine(f"sqlite+pysqlite:///{db_path}")
    with writer.begin() as connection:
        connection.execute(
            users.insert(),
            [
                {"name": "@local:example.com", "is_guest": False, "admin": False, "deactivated": False},
                {
                    "name": "@deactivated:example.com",
                    "is_guest": False,
                    "admin": False,
                    "deactivated": True,
                },
            ],
        )
    writer.dispose()

    engine = build_synapse_engine(f"sqlite+pysqlite:///{db_path}")
    repository = SynapseEventRepository(engine)
    verifier = SenderScopeVerifier(repository)

    try:
        statuses = verifier.verify_senders(
            ["@local:example.com", "@deactivated:example.com", "@remote:elsewhere"],
        )
    finally:
        engine.dispose()

    assert statuses["@local:example.com"].can_redact is True
    assert statuses["@local:example.com"].failure_reason is None

    assert statuses["@deactivated:example.com"].can_redact is False
    assert statuses["@deactivated:example.com"].failure_reason == "local_user_deactivated"

    assert statuses["@remote:elsewhere"].can_redact is False
    assert statuses["@remote:elsewhere"].failure_reason == "remote_user_unsupported"
