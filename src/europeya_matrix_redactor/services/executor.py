from __future__ import annotations

import time
from collections.abc import Callable, Iterable

from europeya_matrix_redactor.clients.matrix_client import MatrixClient, MatrixRequestError
from europeya_matrix_redactor.dto import CandidateEvent, RedactionResult, SenderScopeStatus


class RedactionExecutor:
    def __init__(
        self,
        client_provider: Callable[[str], MatrixClient],
        redaction_reason: str,
        rate_limit_sleep_ms: int,
    ) -> None:
        self.client_provider = client_provider
        self.redaction_reason = redaction_reason
        self.rate_limit_sleep_ms = rate_limit_sleep_ms

    def execute_batch(
        self,
        candidates: Iterable[CandidateEvent],
        sender_scope_map: dict[str, SenderScopeStatus],
    ) -> list[RedactionResult]:
        return [
            self.execute_candidate(candidate, sender_scope_map.get(candidate.sender))
            for candidate in candidates
        ]

    def execute_candidate(
        self,
        candidate: CandidateEvent,
        sender_scope_status: SenderScopeStatus | None,
    ) -> RedactionResult:
        if sender_scope_status is None or not sender_scope_status.can_redact:
            reason = (
                sender_scope_status.failure_reason
                if sender_scope_status is not None
                else "sender_scope_unknown"
            )
            return RedactionResult(
                event_id=candidate.event_id,
                room_id=candidate.room_id,
                sender=candidate.sender,
                success=False,
                retryable=False,
                error_message=f"sender scope failed: {reason}",
            )

        requested = False
        try:
            client = self.client_provider(candidate.sender)
            requested = True
            redaction_event_id = client.redact_event(
                candidate.room_id,
                candidate.event_id,
                self.redaction_reason,
            )
            return RedactionResult(
                event_id=candidate.event_id,
                room_id=candidate.room_id,
                sender=candidate.sender,
                success=True,
                retryable=False,
                redaction_event_id=redaction_event_id,
            )
        except MatrixRequestError as exc:
            return RedactionResult(
                event_id=candidate.event_id,
                room_id=candidate.room_id,
                sender=candidate.sender,
                success=False,
                retryable=exc.retryable,
                http_status=exc.http_status,
                error_message=str(exc),
            )
        finally:
            if requested and self.rate_limit_sleep_ms > 0:
                time.sleep(self.rate_limit_sleep_ms / 1000)
