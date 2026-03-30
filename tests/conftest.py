from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from europeya_matrix_redactor.db.synapse_schema import synapse_metadata


@pytest.fixture
def make_synapse_db(tmp_path: Path):
    created_paths: list[Path] = []

    def factory() -> Path:
        db_path = tmp_path / f"synapse-{len(created_paths)}.db"
        engine = create_engine(f"sqlite+pysqlite:///{db_path}")
        synapse_metadata.create_all(engine)
        engine.dispose()
        created_paths.append(db_path)
        return db_path

    return factory
