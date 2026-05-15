from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, func, insert, or_, outerjoin, select, tuple_, update
from sqlalchemy.engine import Engine

from europeya_matrix_redactor.db.app_state_schema import run_failures, runs
from europeya_matrix_redactor.db.synapse_schema import (
    access_tokens,
    current_state_events,
    events,
    redactions,
    room_memberships,
    user_ips,
    users,
)
from europeya_matrix_redactor.dto import CandidateEvent, RedactionResult, RunMode, RunStatus


def _base_candidate_query(
    cutoff_ms: int,
    allowlist: Sequence[str],
    excluded_room_ids: Sequence[str] = (),
):
    candidate_join = outerjoin(events, redactions, redactions.c.redacts == events.c.event_id)
    query = (
        select(
            events.c.event_id,
            events.c.room_id,
            events.c.sender,
            events.c.origin_server_ts,
            events.c.type.label("event_type"),
        )
        .select_from(candidate_join)
        .where(events.c.origin_server_ts < cutoff_ms)
        .where(events.c.outlier.is_(False))
        .where(events.c.rejection_reason.is_(None))
        .where(events.c.state_key.is_(None))
        .where(events.c.type.in_(tuple(allowlist)))
        .where(redactions.c.redacts.is_(None))
    )
    if excluded_room_ids:
        query = query.where(events.c.room_id.not_in(tuple(excluded_room_ids)))
    return query


class SynapseEventRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def count_candidates(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        excluded_room_ids: Sequence[str] = (),
    ) -> int:
        query = select(func.count()).select_from(
            _base_candidate_query(cutoff_ms, allowlist, excluded_room_ids).subquery(),
        )
        with self.engine.connect() as connection:
            return int(connection.execute(query).scalar_one())

    def count_candidates_by_type(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        excluded_room_ids: Sequence[str] = (),
    ) -> dict[str, int]:
        query = (
            _base_candidate_query(cutoff_ms, allowlist, excluded_room_ids)
            .with_only_columns(
                events.c.type.label("event_type"),
                func.count().label("count"),
            )
            .group_by(events.c.type)
            .order_by(func.count().desc(), events.c.type.asc())
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return {str(row["event_type"]): int(row["count"]) for row in rows}

    def count_candidates_by_room(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        excluded_room_ids: Sequence[str] = (),
    ) -> dict[str, int]:
        query = (
            _base_candidate_query(cutoff_ms, allowlist, excluded_room_ids)
            .with_only_columns(
                events.c.room_id,
                func.count().label("count"),
            )
            .group_by(events.c.room_id)
            .order_by(func.count().desc(), events.c.room_id.asc())
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return {str(row["room_id"]): int(row["count"]) for row in rows}

    def count_candidates_by_sender(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        excluded_room_ids: Sequence[str] = (),
    ) -> dict[str, int]:
        query = (
            _base_candidate_query(cutoff_ms, allowlist, excluded_room_ids)
            .with_only_columns(
                events.c.sender,
                func.count().label("count"),
            )
            .group_by(events.c.sender)
            .order_by(func.count().desc(), events.c.sender.asc())
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return {str(row["sender"]): int(row["count"]) for row in rows}

    def sample_candidates(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        limit: int,
        excluded_room_ids: Sequence[str] = (),
    ) -> list[CandidateEvent]:
        if limit <= 0:
            return []
        query = (
            _base_candidate_query(cutoff_ms, allowlist, excluded_room_ids)
            .order_by(events.c.origin_server_ts.asc(), events.c.event_id.asc())
            .limit(limit)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return [self._row_to_candidate(row) for row in rows]

    def iter_candidates(
        self,
        cutoff_ms: int,
        allowlist: Sequence[str],
        batch_size: int,
        excluded_room_ids: Sequence[str] = (),
    ) -> Iterator[list[CandidateEvent]]:
        last_timestamp: int | None = None
        last_event_id: str | None = None
        with self.engine.connect() as connection:
            while True:
                query = _base_candidate_query(cutoff_ms, allowlist, excluded_room_ids)
                if last_timestamp is not None and last_event_id is not None:
                    query = query.where(
                        or_(
                            events.c.origin_server_ts > last_timestamp,
                            and_(
                                events.c.origin_server_ts == last_timestamp,
                                events.c.event_id > last_event_id,
                            ),
                        ),
                    )
                query = query.order_by(events.c.origin_server_ts.asc(), events.c.event_id.asc()).limit(batch_size)
                rows = connection.execute(query).mappings().all()
                if not rows:
                    break
                batch = [self._row_to_candidate(row) for row in rows]
                last_timestamp = batch[-1].origin_server_ts
                last_event_id = batch[-1].event_id
                yield batch

    def get_sender_profiles(self, user_ids: Iterable[str]) -> dict[str, dict[str, bool]]:
        normalized_user_ids = tuple(sorted(set(user_ids)))
        if not normalized_user_ids:
            return {}

        query = (
            select(users.c.name, users.c.deactivated)
            .where(users.c.name.in_(normalized_user_ids))
            .order_by(users.c.name.asc())
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return {
            str(row["name"]): {"deactivated": bool(row["deactivated"])}
            for row in rows
        }

    def get_sender_tokens(self, user_ids: Iterable[str], now_ms: int) -> dict[str, list[str]]:
        normalized_user_ids = tuple(sorted(set(user_ids)))
        if not normalized_user_ids:
            return {}

        latest_token_activity = (
            select(
                user_ips.c.user_id.label("user_id"),
                user_ips.c.access_token.label("access_token"),
                func.max(user_ips.c.last_seen).label("last_seen"),
            )
            .group_by(user_ips.c.user_id, user_ips.c.access_token)
            .subquery()
        )

        token_activity_join = outerjoin(
            access_tokens,
            latest_token_activity,
            and_(
                access_tokens.c.user_id == latest_token_activity.c.user_id,
                access_tokens.c.token == latest_token_activity.c.access_token,
            ),
        )
        query = (
            select(
                access_tokens.c.user_id,
                access_tokens.c.token,
                access_tokens.c.last_validated,
                access_tokens.c.id,
                latest_token_activity.c.last_seen,
            )
            .select_from(token_activity_join)
            .where(access_tokens.c.user_id.in_(normalized_user_ids))
            .where(access_tokens.c.token != "")
            .where(access_tokens.c.puppets_user_id.is_(None))
            .where(
                or_(
                    access_tokens.c.valid_until_ms.is_(None),
                    access_tokens.c.valid_until_ms > now_ms,
                ),
            )
            .order_by(
                access_tokens.c.user_id.asc(),
                latest_token_activity.c.last_seen.desc().nulls_last(),
                access_tokens.c.last_validated.desc().nulls_last(),
                access_tokens.c.id.desc(),
            )
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()

        tokens_by_user: dict[str, list[str]] = {}
        for row in rows:
            user_id = str(row["user_id"])
            token = str(row["token"])
            tokens_by_user.setdefault(user_id, []).append(token)
        return tokens_by_user

    def get_joined_room_memberships(
        self,
        sender_room_pairs: Iterable[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        normalized_pairs = tuple(sorted(set(sender_room_pairs)))
        if not normalized_pairs:
            return set()

        membership_join = current_state_events.join(
            room_memberships,
            room_memberships.c.event_id == current_state_events.c.event_id,
        )
        query = (
            select(
                current_state_events.c.state_key.label("user_id"),
                current_state_events.c.room_id,
            )
            .select_from(membership_join)
            .where(current_state_events.c.type == "m.room.member")
            .where(room_memberships.c.membership == "join")
            .where(
                tuple_(
                    current_state_events.c.state_key,
                    current_state_events.c.room_id,
                ).in_(normalized_pairs),
            )
        )
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return {
            (str(row["user_id"]), str(row["room_id"]))
            for row in rows
        }

    @staticmethod
    def _row_to_candidate(row) -> CandidateEvent:
        return CandidateEvent(
            event_id=str(row["event_id"]),
            room_id=str(row["room_id"]),
            sender=str(row["sender"]),
            origin_server_ts=int(row["origin_server_ts"]),
            event_type=str(row["event_type"]),
        )


class RunJournalRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def start_run(self, run_mode: RunMode, cutoff_ms: int) -> int:
        statement = insert(runs).values(
            started_at=datetime.now(UTC),
            run_mode=run_mode.value,
            status=RunStatus.RUNNING.value,
            cutoff_ms=cutoff_ms,
            candidate_count=0,
            processed_count=0,
            successful_redactions=0,
            skipped_count=0,
            failure_count=0,
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return int(result.inserted_primary_key[0])

    def finish_run(
        self,
        run_id: int,
        status: RunStatus,
        candidate_count: int,
        processed_count: int,
        successful_redactions: int,
        skipped_count: int,
        failure_count: int,
        summary: dict[str, object] | None = None,
        error_message: str | None = None,
    ) -> None:
        statement = (
            update(runs)
            .where(runs.c.id == run_id)
            .values(
                finished_at=datetime.now(UTC),
                status=status.value,
                candidate_count=candidate_count,
                processed_count=processed_count,
                successful_redactions=successful_redactions,
                skipped_count=skipped_count,
                failure_count=failure_count,
                summary_json=summary,
                error_message=error_message,
            )
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def record_failure(
        self,
        run_id: int,
        failure_kind: str,
        error_message: str,
        *,
        event_id: str | None = None,
        room_id: str | None = None,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        statement = insert(run_failures).values(
            run_id=run_id,
            created_at=datetime.now(UTC),
            failure_kind=failure_kind,
            event_id=event_id,
            room_id=room_id,
            retryable=retryable,
            http_status=http_status,
            error_message=error_message,
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def record_redaction_result(self, run_id: int, result: RedactionResult) -> None:
        if result.success:
            return
        self.record_failure(
            run_id=run_id,
            failure_kind=result.failure_kind or "redaction_request",
            event_id=result.event_id,
            room_id=result.room_id,
            retryable=result.retryable,
            http_status=result.http_status,
            error_message=result.error_message or "redaction request failed",
        )
