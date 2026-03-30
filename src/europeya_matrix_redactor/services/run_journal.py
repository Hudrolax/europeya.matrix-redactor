from __future__ import annotations

from europeya_matrix_redactor.dto import RedactionResult, RunMode, RunStatus


class RunJournalService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def start_run(self, run_mode: RunMode, cutoff_ms: int) -> int:
        return self.repository.start_run(run_mode, cutoff_ms)

    def finish_run(
        self,
        run_id: int,
        status: RunStatus,
        *,
        candidate_count: int,
        processed_count: int,
        successful_redactions: int,
        skipped_count: int,
        failure_count: int,
        summary: dict[str, object] | None = None,
        error_message: str | None = None,
    ) -> None:
        self.repository.finish_run(
            run_id=run_id,
            status=status,
            candidate_count=candidate_count,
            processed_count=processed_count,
            successful_redactions=successful_redactions,
            skipped_count=skipped_count,
            failure_count=failure_count,
            summary=summary,
            error_message=error_message,
        )

    def record_failure(
        self,
        run_id: int,
        *,
        failure_kind: str,
        error_message: str,
        event_id: str | None = None,
        room_id: str | None = None,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        self.repository.record_failure(
            run_id=run_id,
            failure_kind=failure_kind,
            error_message=error_message,
            event_id=event_id,
            room_id=room_id,
            retryable=retryable,
            http_status=http_status,
        )

    def record_redaction_result(self, run_id: int, result: RedactionResult) -> None:
        self.repository.record_redaction_result(run_id, result)
