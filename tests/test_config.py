from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from europeya_matrix_redactor.config import load_config


def test_config_normalizes_allowlist_and_base_url(tmp_path: Path) -> None:
    config = load_config(
        None,
        synapse_base_url="http://synapse.local/",
        synapse_db_url="sqlite+pysqlite:////tmp/synapse.db",
        event_type_allowlist=" m.room.message, m.room.encrypted ,, ",
        room_id_excludelist=" !room-a:example.com, !room-b:example.com ,, ",
        lock_file_path=tmp_path / "run.lock",
    )

    assert config.synapse_base_url == "http://synapse.local"
    assert config.event_type_allowlist == ("m.room.message", "m.room.encrypted")
    assert config.room_id_excludelist == ("!room-a:example.com", "!room-b:example.com")
    assert config.max_concurrent_senders == 8
    assert config.rate_limit_sleep_ms == 0


def test_config_rejects_invalid_cron_schedule(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_config(
            None,
            synapse_base_url="http://synapse.local",
            synapse_db_url="sqlite+pysqlite:////tmp/synapse.db",
            cron_schedule="not a cron",
            lock_file_path=tmp_path / "run.lock",
        )


def test_explicit_env_file_overrides_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                "SYNAPSE_BASE_URL=http://synapse.from.file",
                "SYNAPSE_DB_URL=sqlite+pysqlite:////tmp/from-file.db",
                "TTL_HOURS=12",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNAPSE_BASE_URL", "http://synapse.from.env")
    monkeypatch.setenv("SYNAPSE_DB_URL", "sqlite+pysqlite:////tmp/from-env.db")
    monkeypatch.setenv("TTL_HOURS", "24")

    config = load_config(env_file)

    assert config.synapse_base_url == "http://synapse.from.file"
    assert config.synapse_db_url == "sqlite+pysqlite:////tmp/from-file.db"
    assert config.ttl_hours == 12
