from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence

from europeya_matrix_redactor.clients.matrix_client import MatrixClient, MatrixRequestError
from europeya_matrix_redactor.config import AppConfig, load_config
from europeya_matrix_redactor.db.engine import (
    build_app_state_engine,
    build_synapse_engine,
    ensure_app_state_schema,
    ping_database,
)
from europeya_matrix_redactor.db.repositories import RunJournalRepository, SynapseEventRepository
from europeya_matrix_redactor.dto import SenderScopeStatus, RunMode, RunStatus
from europeya_matrix_redactor.locks import FileLock, LockAcquisitionError
from europeya_matrix_redactor.logging import configure_logging, get_logger
from europeya_matrix_redactor.scheduler import write_crontab
from europeya_matrix_redactor.services.executor import RedactionExecutor
from europeya_matrix_redactor.services.planner import RedactionPlanner
from europeya_matrix_redactor.services.room_access import SenderScopeVerifier
from europeya_matrix_redactor.services.run_journal import RunJournalService

DEFAULT_SAMPLE_SIZE = 10


class SenderTokenClient:
    def __init__(
        self,
        *,
        base_url: str,
        access_tokens: Sequence[str],
        timeout_seconds: float,
        max_retries: int,
        rate_limit_sleep_ms: int,
    ) -> None:
        self._clients = [
            MatrixClient(
                base_url=base_url,
                access_token=access_token,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                rate_limit_sleep_ms=rate_limit_sleep_ms,
            )
            for access_token in access_tokens
        ]

    def redact_event(self, room_id: str, event_id: str, reason: str) -> str | None:
        last_error: MatrixRequestError | None = None
        for client in self._clients:
            try:
                return client.redact_event(room_id, event_id, reason)
            except MatrixRequestError as exc:
                last_error = exc
                if exc.http_status == 401 or exc.errcode == "M_UNKNOWN_TOKEN":
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise MatrixRequestError(
            message="sender has no usable access token",
            retryable=False,
        )

    def close(self) -> None:
        for client in self._clients:
            client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matrix-redactor")
    parser.add_argument("--env-file", default=None, help="Path to .env file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_once = subparsers.add_parser("run-once", help="Execute one sweep")
    run_mode = run_once.add_mutually_exclusive_group()
    run_mode.add_argument("--dry-run", action="store_true", help="Override config and force dry-run")
    run_mode.add_argument("--real-run", action="store_true", help="Override config and force real run")
    run_once.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)

    dry_run_report = subparsers.add_parser("dry-run-report", help="Print dry-run summary")
    dry_run_report.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)

    subparsers.add_parser("healthcheck", help="Validate DB and Matrix connectivity")

    render_crontab = subparsers.add_parser("render-crontab", help="Render supercronic crontab file")
    render_crontab.add_argument("--output", required=True, help="Destination path for the crontab")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.env_file)
    configure_logging(config.log_level)

    if args.command == "healthcheck":
        return run_healthcheck(config)
    if args.command == "render-crontab":
        return run_render_crontab(config, output_path=args.output)
    if args.command == "dry-run-report":
        return run_once(config, dry_run_override=True, sample_size=args.sample_size, print_report=True)
    if args.command == "run-once":
        dry_run_override = True if args.dry_run else False if args.real_run else None
        should_print_report = args.dry_run or (not args.real_run and config.dry_run)
        return run_once(
            config,
            dry_run_override=dry_run_override,
            sample_size=args.sample_size,
            print_report=should_print_report,
        )

    parser.error(f"Unsupported command: {args.command}")
    return 2


def run_once(
    config: AppConfig,
    *,
    dry_run_override: bool | None,
    sample_size: int,
    print_report: bool,
) -> int:
    logger = get_logger(__name__)
    dry_run = config.dry_run if dry_run_override is None else dry_run_override
    run_mode = RunMode.DRY_RUN if dry_run else RunMode.REAL_RUN

    app_state_engine = build_app_state_engine(config.app_state_db_url)
    ensure_app_state_schema(app_state_engine)
    journal = RunJournalService(RunJournalRepository(app_state_engine))

    synapse_engine = build_synapse_engine(config.synapse_db_url)
    event_repository = SynapseEventRepository(synapse_engine)
    planner = RedactionPlanner(
        event_repository,
        SenderScopeVerifier(event_repository),
    )
    cutoff_ms = planner.calculate_cutoff_ms(config.ttl_hours)

    try:
        with FileLock(config.lock_file_path):
            run_id = journal.start_run(run_mode, cutoff_ms)
            logger.info("run started", extra={"run_id": run_id, "run_mode": run_mode.value})
            return _execute_locked_run(
                config,
                planner,
                journal,
                run_id,
                run_mode,
                cutoff_ms,
                sample_size=sample_size,
                print_report=print_report,
            )
    except LockAcquisitionError as exc:
        logger.warning("run skipped due to lock", extra={"lock_file": str(config.lock_file_path)})
        skipped_run_id = journal.start_run(run_mode, cutoff_ms)
        journal.finish_run(
            skipped_run_id,
            RunStatus.SKIPPED,
            candidate_count=0,
            processed_count=0,
            successful_redactions=0,
            skipped_count=0,
            failure_count=0,
            summary={"reason": str(exc), "lock_file": str(config.lock_file_path)},
            error_message=str(exc),
        )
        print(json.dumps({"status": "skipped", "reason": str(exc)}, ensure_ascii=True))
        return 0
    finally:
        synapse_engine.dispose()
        app_state_engine.dispose()


def _execute_locked_run(
    config: AppConfig,
    planner: RedactionPlanner,
    journal: RunJournalService,
    run_id: int,
    run_mode: RunMode,
    cutoff_ms: int,
    *,
    sample_size: int,
    print_report: bool,
) -> int:
    logger = get_logger(__name__)
    report = None
    summary: dict[str, object] = {}
    sender_scope_map: dict[str, SenderScopeStatus] = {}
    success_count = 0
    skipped_count = 0
    failure_count = 0
    processed_count = 0
    current_time_ms = int(time.time() * 1000)

    try:
        report = planner.build_dry_run_report(
            cutoff_ms=cutoff_ms,
            allowlist=config.event_type_allowlist,
            sample_size=sample_size,
            now_ms=current_time_ms,
        )
        summary = report.as_dict()
        sender_scope_map = dict(report.sender_scope)

        if run_mode is RunMode.DRY_RUN:
            journal.finish_run(
                run_id,
                RunStatus.COMPLETED,
                candidate_count=report.total_candidates,
                processed_count=0,
                successful_redactions=0,
                skipped_count=0,
                failure_count=0,
                summary=summary,
            )
            if print_report:
                print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
            return 0

        sender_tokens = planner.event_repository.get_sender_tokens(
            (
                sender_id
                for sender_id, status in sender_scope_map.items()
                if status.can_redact
            ),
            current_time_ms,
        )
        sender_clients: dict[str, SenderTokenClient] = {}

        def get_client_for_sender(sender: str) -> SenderTokenClient:
            cached_client = sender_clients.get(sender)
            if cached_client is not None:
                return cached_client

            access_tokens = sender_tokens.get(sender, [])
            if not access_tokens:
                raise MatrixRequestError(
                    message=f"no valid access token for {sender}",
                    retryable=False,
                )

            client = SenderTokenClient(
                base_url=config.synapse_base_url,
                access_tokens=access_tokens,
                timeout_seconds=config.request_timeout_seconds,
                max_retries=config.max_retries,
                rate_limit_sleep_ms=config.rate_limit_sleep_ms,
            )
            sender_clients[sender] = client
            return client

        executor = RedactionExecutor(
            client_provider=get_client_for_sender,
            redaction_reason=config.redaction_reason,
            rate_limit_sleep_ms=config.rate_limit_sleep_ms,
        )
        try:
            for batch in planner.iter_candidate_batches(
                cutoff_ms=cutoff_ms,
                allowlist=config.event_type_allowlist,
                batch_size=config.batch_size,
            ):
                processed_count += len(batch)
                membership_checked_candidates = [
                    candidate
                    for candidate in batch
                    if (sender_status := sender_scope_map.get(candidate.sender)) is not None
                    and sender_status.can_redact
                ]
                room_membership_failures = planner.sender_scope_verifier.find_room_membership_failures(
                    membership_checked_candidates,
                )

                for result in executor.execute_batch(
                    batch,
                    sender_scope_map,
                    room_membership_failures,
                ):
                    if result.success:
                        success_count += 1
                        continue

                    if result.failure_kind in {"sender_scope", "room_membership"}:
                        skipped_count += 1
                        journal.record_failure(
                            run_id,
                            failure_kind=result.failure_kind or "skipped",
                            room_id=result.room_id,
                            event_id=result.event_id,
                            error_message=result.error_message or "candidate skipped",
                        )
                        continue

                    failure_count += 1
                    journal.record_redaction_result(run_id, result)
        finally:
            for client in sender_clients.values():
                client.close()

        completed_summary = {
            **summary,
            "processed_count": processed_count,
            "successful_redactions": success_count,
            "skipped_count": skipped_count,
            "failure_count": failure_count,
        }
        journal.finish_run(
            run_id,
            RunStatus.COMPLETED if failure_count == 0 else RunStatus.FAILED,
            candidate_count=report.total_candidates,
            processed_count=processed_count,
            successful_redactions=success_count,
            skipped_count=skipped_count,
            failure_count=failure_count,
            summary=completed_summary,
            error_message=None if failure_count == 0 else "run completed with failures",
        )
        logger.info(
            "run completed",
            extra={
                "run_id": run_id,
                "candidate_count": report.total_candidates,
                "processed_count": processed_count,
                "successful_redactions": success_count,
                "skipped_count": skipped_count,
                "failure_count": failure_count,
            },
        )
        print(json.dumps(completed_summary, ensure_ascii=True))
        return 0 if failure_count == 0 else 1
    except Exception as exc:
        journal.finish_run(
            run_id,
            RunStatus.FAILED,
            candidate_count=report.total_candidates if report is not None else 0,
            processed_count=processed_count,
            successful_redactions=success_count,
            skipped_count=skipped_count,
            failure_count=failure_count + 1,
            summary=summary or None,
            error_message=str(exc),
        )
        logger.exception("run failed", extra={"run_id": run_id})
        raise


def run_healthcheck(config: AppConfig) -> int:
    synapse_engine = build_synapse_engine(config.synapse_db_url)
    app_state_engine = build_app_state_engine(config.app_state_db_url)
    ensure_app_state_schema(app_state_engine)

    try:
        ping_database(synapse_engine)
        ping_database(app_state_engine)
        with MatrixClient(
            base_url=config.synapse_base_url,
            access_token=None,
            timeout_seconds=config.request_timeout_seconds,
            max_retries=config.max_retries,
            rate_limit_sleep_ms=config.rate_limit_sleep_ms,
        ) as matrix_client:
            result = matrix_client.healthcheck()
        print(json.dumps({"status": "ok", "matrix": result}, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=True))
        return 1
    finally:
        synapse_engine.dispose()
        app_state_engine.dispose()


def run_render_crontab(config: AppConfig, *, output_path: str) -> int:
    path = write_crontab(output_path, config.cron_schedule, timezone=config.timezone)
    print(json.dumps({"status": "ok", "crontab_path": str(path)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
