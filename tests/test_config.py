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
        synapse_admin_access_token="secret",
        event_type_allowlist=" m.room.message, m.room.encrypted ,, ",
        lock_file_path=tmp_path / "run.lock",
    )

    assert config.synapse_base_url == "http://synapse.local"
    assert config.event_type_allowlist == ("m.room.message", "m.room.encrypted")


def test_config_requires_admin_access_token(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_config(
            None,
            synapse_base_url="http://synapse.local",
            synapse_db_url="sqlite+pysqlite:////tmp/synapse.db",
            lock_file_path=tmp_path / "run.lock",
        )


def test_config_rejects_invalid_cron_schedule(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_config(
            None,
            synapse_base_url="http://synapse.local",
            synapse_db_url="sqlite+pysqlite:////tmp/synapse.db",
            synapse_admin_access_token="secret",
            cron_schedule="not a cron",
            lock_file_path=tmp_path / "run.lock",
        )
