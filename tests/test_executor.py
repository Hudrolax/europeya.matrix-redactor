from __future__ import annotations

import httpx
import pytest

from europeya_matrix_redactor.clients.matrix_client import MatrixClient, MatrixRequestError
from europeya_matrix_redactor.dto import CandidateEvent, SenderScopeStatus
from europeya_matrix_redactor.services.executor import RedactionExecutor


def test_matrix_client_can_issue_impersonation_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"access_token": "child-token"})

    with MatrixClient(
        base_url="http://synapse.local",
        access_token="admin-token",
        timeout_seconds=1,
        max_retries=1,
        rate_limit_sleep_ms=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        access_token = client.login_as_user("@alice:example.com", valid_until_ms=123456)

    assert access_token == "child-token"
    assert requests[-1].headers["Authorization"] == "Bearer admin-token"
    assert "%40alice%3Aexample.com" in str(requests[-1].url)
    assert requests[-1].content == b'{"valid_until_ms":123456}'


def test_matrix_client_retries_on_rate_limit_and_redacts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                json={
                    "errcode": "M_LIMIT_EXCEEDED",
                    "error": "slow down",
                    "retry_after_ms": 0,
                },
            )
        return httpx.Response(200, json={"event_id": "$redaction"})

    with MatrixClient(
        base_url="http://synapse.local",
        access_token="secret-token",
        timeout_seconds=1,
        max_retries=1,
        rate_limit_sleep_ms=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        redaction_event_id = client.redact_event(
            "!room:example.com",
            "$event:example.com",
            "Expired by policy",
        )

    assert redaction_event_id == "$redaction"
    assert len(requests) == 2
    assert requests[-1].headers["Authorization"] == "Bearer secret-token"
    assert "%21room%3Aexample.com" in str(requests[-1].url)
    assert "%24event%3Aexample.com" in str(requests[-1].url)


def test_matrix_client_marks_forbidden_as_permanent_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "errcode": "M_FORBIDDEN",
                "error": "forbidden",
            },
        )

    with MatrixClient(
        base_url="http://synapse.local",
        access_token="secret-token",
        timeout_seconds=1,
        max_retries=1,
        rate_limit_sleep_ms=0,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(MatrixRequestError) as exc_info:
            client.redact_event("!room:example.com", "$event:example.com", "Expired by policy")

    assert exc_info.value.retryable is False
    assert exc_info.value.http_status == 403


def test_redaction_executor_skips_remote_sender() -> None:
    class UnexpectedClient:
        def redact_event(self, room_id: str, event_id: str, reason: str) -> str:
            raise AssertionError(f"unexpected redaction call for {room_id} {event_id} {reason}")

    executor = RedactionExecutor(
        client_provider=lambda sender: UnexpectedClient(),  # type: ignore[arg-type]
        redaction_reason="Expired by policy",
        rate_limit_sleep_ms=0,
    )
    candidate = CandidateEvent(
        event_id="$event",
        room_id="!room:example.com",
        sender="@remote:elsewhere",
        origin_server_ts=100,
        event_type="m.room.message",
    )
    status = SenderScopeStatus(
        user_id="@remote:elsewhere",
        is_local=False,
        is_active=False,
        mode="local_user_impersonation",
        failure_reason="remote_user_unsupported",
    )

    result = executor.execute_candidate(candidate, status)

    assert result.success is False
    assert result.retryable is False
    assert result.error_message == "sender scope failed: remote_user_unsupported"
