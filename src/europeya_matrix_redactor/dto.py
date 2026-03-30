from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class RedactionMode(StrEnum):
    LOCAL_USER_ACCESS_TOKEN = "local_user_access_token"


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    REAL_RUN = "real_run"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CandidateEvent:
    event_id: str
    room_id: str
    sender: str
    origin_server_ts: int
    event_type: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SenderScopeStatus:
    user_id: str
    is_local: bool
    is_active: bool
    has_access_token: bool
    mode: str
    failure_reason: str | None = None

    @property
    def can_redact(self) -> bool:
        return (
            self.is_local
            and self.is_active
            and self.has_access_token
            and self.failure_reason is None
        )

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["can_redact"] = self.can_redact
        return payload


@dataclass(frozen=True, slots=True)
class RedactionResult:
    event_id: str
    room_id: str
    sender: str
    success: bool
    retryable: bool
    http_status: int | None = None
    error_message: str | None = None
    redaction_event_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DryRunReport:
    cutoff_ms: int
    total_candidates: int
    counts_by_type: dict[str, int]
    counts_by_room: dict[str, int]
    counts_by_sender: dict[str, int]
    sender_scope: dict[str, SenderScopeStatus]
    sample_candidates: list[CandidateEvent] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "cutoff_ms": self.cutoff_ms,
            "total_candidates": self.total_candidates,
            "counts_by_type": self.counts_by_type,
            "counts_by_room": self.counts_by_room,
            "counts_by_sender": self.counts_by_sender,
            "sender_scope": {
                user_id: status.as_dict()
                for user_id, status in self.sender_scope.items()
            },
            "sample_candidates": [candidate.as_dict() for candidate in self.sample_candidates],
        }
