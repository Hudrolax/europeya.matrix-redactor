from __future__ import annotations

from pathlib import Path

import pytest

from europeya_matrix_redactor.cli import _execute_locked_run, main
from europeya_matrix_redactor.config import AppConfig
from europeya_matrix_redactor.dto import DryRunReport, RunMode, RunStatus


class _RecordingJournal:
    def __init__(self) -> None:
        self.finish_calls: list[dict[str, object]] = []

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
        summary: dict[str, object] | None,
        error_message: str | None,
    ) -> None:
        self.finish_calls.append(
            {
                "run_id": run_id,
                "status": status,
                "candidate_count": candidate_count,
                "processed_count": processed_count,
                "successful_redactions": successful_redactions,
                "skipped_count": skipped_count,
                "failure_count": failure_count,
                "summary": summary,
                "error_message": error_message,
            }
        )

    def record_failure(self, *args, **kwargs) -> None:  # pragma: no cover
        raise AssertionError("record_failure should not be called")

    def record_redaction_result(self, *args, **kwargs) -> None:  # pragma: no cover
        raise AssertionError("record_redaction_result should not be called")


class _FakeEventRepository:
    def get_sender_tokens(self, user_ids, now_ms: int) -> dict[str, list[str]]:
        return {}


class _InterruptingPlanner:
    def __init__(self) -> None:
        self.event_repository = _FakeEventRepository()
        self.sender_scope_verifier = None

    def build_dry_run_report(
        self,
        cutoff_ms: int,
        allowlist: tuple[str, ...],
        sample_size: int,
        now_ms: int,
    ) -> DryRunReport:
        return DryRunReport(
            cutoff_ms=cutoff_ms,
            total_candidates=1,
            counts_by_type={"m.room.message": 1},
            counts_by_room={"!room:example.com": 1},
            counts_by_sender={"@alice:example.com": 1},
            sender_scope={},
            sample_candidates=[],
        )

    def iter_candidate_batches(self, cutoff_ms: int, allowlist: tuple[str, ...], batch_size: int):
        raise KeyboardInterrupt("stop requested")
        yield  # pragma: no cover


def test_execute_locked_run_marks_keyboard_interrupt_as_failed(tmp_path: Path) -> None:
    config = AppConfig(
        SYNAPSE_BASE_URL="http://synapse.local",
        SYNAPSE_DB_URL="sqlite+pysqlite:////tmp/synapse.db",
        APP_STATE_DB_URL="sqlite+pysqlite:////tmp/state.db",
        LOCK_FILE_PATH=tmp_path / "run.lock",
        DRY_RUN=False,
        RATE_LIMIT_SLEEP_MS=0,
    )
    planner = _InterruptingPlanner()
    journal = _RecordingJournal()

    with pytest.raises(KeyboardInterrupt, match="stop requested"):
        _execute_locked_run(
            config,
            planner,
            journal,
            run_id=7,
            run_mode=RunMode.REAL_RUN,
            cutoff_ms=123,
            sample_size=5,
            print_report=False,
        )

    assert journal.finish_calls == [
        {
            "run_id": 7,
            "status": RunStatus.FAILED,
            "candidate_count": 1,
            "processed_count": 0,
            "successful_redactions": 0,
            "skipped_count": 0,
            "failure_count": 1,
            "summary": {
                "cutoff_ms": 123,
                "total_candidates": 1,
                "counts_by_type": {"m.room.message": 1},
                "counts_by_room": {"!room:example.com": 1},
                "counts_by_sender": {"@alice:example.com": 1},
                "sender_scope": {},
                "sample_candidates": [],
            },
            "error_message": "stop requested",
        }
    ]


def test_main_logs_runtime_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env_file = tmp_path / "runtime.env"
    output_file = tmp_path / "crontab"
    env_file.write_text(
        "\n".join(
            [
                "SYNAPSE_BASE_URL=http://synapse.local",
                "SYNAPSE_DB_URL=sqlite+pysqlite:////tmp/synapse.db",
                "TTL_HOURS=12",
                "CRON_SCHEDULE=0 5 * * *",
                "TZ=Europe/Moscow",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--env-file",
            str(env_file),
            "render-crontab",
            "--output",
            str(output_file),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"message": "runtime config loaded"' in captured.err
    assert '"ttl_hours": 12' in captured.err
    assert '"cron_schedule": "0 5 * * *"' in captured.err
