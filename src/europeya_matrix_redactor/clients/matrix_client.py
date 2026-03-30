from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(slots=True)
class MatrixRequestError(Exception):
    message: str
    retryable: bool
    http_status: int | None = None
    errcode: str | None = None

    def __str__(self) -> str:
        if self.http_status is None:
            return self.message
        return f"{self.message} (status={self.http_status})"


class MatrixClient:
    def __init__(
        self,
        base_url: str,
        access_token: str | None,
        timeout_seconds: float,
        max_retries: int,
        rate_limit_sleep_ms: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.rate_limit_sleep_ms = rate_limit_sleep_ms
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "europeya-matrix-redactor/0.1.0"},
            transport=transport,
        )

    def __enter__(self) -> "MatrixClient":
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self.close()
        return None

    def close(self) -> None:
        self._client.close()

    def healthcheck(self) -> dict[str, object]:
        payload = self._request_json("GET", "/_matrix/client/versions", authenticated=False)
        result: dict[str, object] = {"versions": payload.get("versions", [])}
        if self.access_token:
            whoami = self._request_json("GET", "/_matrix/client/v3/account/whoami")
            result["whoami"] = whoami.get("user_id")
        return result

    def login_as_user(self, user_id: str, *, valid_until_ms: int | None = None) -> str:
        path = f"/_synapse/admin/v1/users/{quote(user_id, safe='')}/login"
        payload: dict[str, object] = {}
        if valid_until_ms is not None:
            payload["valid_until_ms"] = valid_until_ms
        response = self._request_json("POST", path, json=payload)
        access_token = response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise MatrixRequestError(
                message="Synapse admin login did not return access_token",
                retryable=False,
            )
        return access_token

    def redact_event(self, room_id: str, event_id: str, reason: str) -> str | None:
        txn_id = uuid.uuid4().hex
        path = (
            f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}"
            f"/redact/{quote(event_id, safe='')}/{txn_id}"
        )
        payload = self._request_json("PUT", path, json={"reason": reason})
        return payload.get("event_id")

    def logout(self) -> None:
        self._request_json("POST", "/_matrix/client/v3/logout", json={})

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {}
        if authenticated:
            if not self.access_token:
                raise MatrixRequestError(
                    message="Matrix access token is not configured",
                    retryable=False,
                )
            headers["Authorization"] = f"Bearer {self.access_token}"

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(method, path, json=json, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.max_retries:
                    raise MatrixRequestError(str(exc), retryable=True) from exc
                self._sleep_before_retry(attempt)
                continue

            if response.status_code < 400:
                if not response.content:
                    return {}
                return response.json()

            error_payload = _extract_error_payload(response)
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < self.max_retries:
                self._sleep_retryable_response(response, error_payload, attempt)
                continue

            raise MatrixRequestError(
                message=error_payload.get("error") or response.text or "Matrix request failed",
                retryable=retryable,
                http_status=response.status_code,
                errcode=error_payload.get("errcode"),
            )

        raise MatrixRequestError("Matrix request retry loop exhausted", retryable=True)

    def _sleep_retryable_response(
        self,
        response: httpx.Response,
        error_payload: dict[str, Any],
        attempt: int,
    ) -> None:
        if response.status_code == 429:
            retry_after_ms = error_payload.get("retry_after_ms")
            if isinstance(retry_after_ms, int) and retry_after_ms >= 0:
                time.sleep(retry_after_ms / 1000)
                return
            if self.rate_limit_sleep_ms > 0:
                time.sleep(self.rate_limit_sleep_ms / 1000)
                return
        self._sleep_before_retry(attempt)

    @staticmethod
    def _sleep_before_retry(attempt: int) -> None:
        time.sleep(min(5.0, 0.5 * (2**attempt)))


def _extract_error_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}
