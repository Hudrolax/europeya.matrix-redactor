from __future__ import annotations

import fcntl
import os
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO


class LockAcquisitionError(RuntimeError):
    """Raised when another run already holds the lock."""


@dataclass(slots=True)
class FileLock(AbstractContextManager["FileLock"]):
    path: Path
    handle: TextIO | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise LockAcquisitionError(f"lock already held: {self.path}") from exc

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(
            f"pid={os.getpid()} acquired_at={datetime.now(UTC).isoformat()}\n",
        )
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self.handle is None:
            return None
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
        return None
