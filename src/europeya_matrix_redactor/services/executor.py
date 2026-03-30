from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping

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
        room_membership_failures: Mapping[str, str] | None = None,
    ) -> list[RedactionResult]:
        return [
            self.execute_candidate(
                candidate,
                sender_scope_map.get(candidate.sender),
                None if room_membership_failures is None else room_membership_failures.get(candidate.event_id),
            )
            for candidate in candidates
        ]

    def execute_candidate(
        self,
        candidate: CandidateEvent,
        sender_scope_status: SenderScopeStatus | None,
        room_membership_failure_reason: str | None = None,
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
                failure_kind="sender_scope",
                error_message=f"sender scope failed: {reason}",
            )

        if room_membership_failure_reason is not None:
            return RedactionResult(
                event_id=candidate.event_id,
                room_id=candidate.room_id,
                sender=candidate.sender,
                success=False,
                retryable=False,
                failure_kind="room_membership",
                error_message=f"room membership failed: {room_membership_failure_reason}",
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
                failure_kind="redaction_request",
                http_status=exc.http_status,
                error_message=str(exc),
            )
        finally:
            if requested and self.rate_limit_sleep_ms > 0:
                time.sleep(self.rate_limit_sleep_ms / 1000)
