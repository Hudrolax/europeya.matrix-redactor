from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta

from europeya_matrix_redactor.dto import CandidateEvent, DryRunReport


class RedactionPlanner:
    def __init__(self, event_repository, sender_scope_verifier) -> None:
        self.event_repository = event_repository
        self.sender_scope_verifier = sender_scope_verifier

    @staticmethod
    def calculate_cutoff_ms(ttl_hours: int, now: datetime | None = None) -> int:
        current_time = now or datetime.now(UTC)
        cutoff = current_time - timedelta(hours=ttl_hours)
        return int(cutoff.timestamp() * 1000)

    def build_dry_run_report(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        sample_size: int,
        now_ms: int,
    ) -> DryRunReport:
        total_candidates = self.event_repository.count_candidates(cutoff_ms, allowlist)
        counts_by_type = self.event_repository.count_candidates_by_type(cutoff_ms, allowlist)
        counts_by_room = self.event_repository.count_candidates_by_room(cutoff_ms, allowlist)
        counts_by_sender = self.event_repository.count_candidates_by_sender(cutoff_ms, allowlist)
        sender_scope = self.sender_scope_verifier.verify_senders(counts_by_sender.keys(), now_ms)
        sample_candidates = self.event_repository.sample_candidates(cutoff_ms, allowlist, sample_size)
        return DryRunReport(
            cutoff_ms=cutoff_ms,
            total_candidates=total_candidates,
            counts_by_type=counts_by_type,
            counts_by_room=counts_by_room,
            counts_by_sender=counts_by_sender,
            sender_scope=sender_scope,
            sample_candidates=sample_candidates,
        )

    def iter_candidate_batches(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        batch_size: int,
    ) -> Iterator[list[CandidateEvent]]:
        yield from self.event_repository.iter_candidates(cutoff_ms, allowlist, batch_size)
