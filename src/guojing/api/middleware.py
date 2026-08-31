"""ASGI guards for privacy-sensitive help-request HTTP boundaries."""

import json
from collections import deque
from threading import Lock
from time import monotonic

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HELP_REQUEST_PATH_PREFIX = "/api/v1/help-requests"
MAX_HELP_REQUEST_BODY_BYTES = 12 * 1024 * 1024
HELP_REQUEST_RATE_WINDOW_SECONDS = 60.0
HELP_REQUEST_RATE_LIMIT = 30


class HelpRequestSecurityMiddleware:
    """Limit request bytes and add no-store headers before FastAPI parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int = MAX_HELP_REQUEST_BODY_BYTES,
        rate_limit: int = HELP_REQUEST_RATE_LIMIT,
        rate_window_seconds: float = HELP_REQUEST_RATE_WINDOW_SECONDS,
    ) -> None:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes
        if rate_limit < 1 or rate_window_seconds <= 0:
            raise ValueError("rate limit settings must be positive")
        self.rate_limit = rate_limit
        self.rate_window_seconds = rate_window_seconds
        self._rate_lock = Lock()
        self._requests_by_client: dict[str, deque[float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_help_request_scope(scope):
            await self.app(scope, receive, send)
            return

        if _is_submission_scope(scope) and not self._allow_submission(scope):
            await _send_rate_limited(send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await _send_too_large(send)
            return

        received_bytes = 0
        response_started = False

        async def guarded_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] != "http.request":
                return message
            received_bytes += len(message.get("body", b""))
            if received_bytes > self.max_body_bytes:
                raise _RequestBodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                _append_header_if_missing(headers, b"cache-control", b"no-store")
                _append_header_if_missing(headers, b"pragma", b"no-cache")
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, guarded_receive, guarded_send)
        except _RequestBodyTooLarge:
            if not response_started:
                await _send_too_large(send)

    def _allow_submission(self, scope: Scope) -> bool:
        client = scope.get("client")
        client_id = str(client[0]) if isinstance(client, (tuple, list)) and client else "unknown"
        now = monotonic()
        with self._rate_lock:
            timestamps = self._requests_by_client.setdefault(client_id, deque())
            cutoff = now - self.rate_window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.rate_limit:
                return False
            timestamps.append(now)
            if len(self._requests_by_client) > 10_000:
                self._requests_by_client = {
                    key: value
                    for key, value in self._requests_by_client.items()
                    if value and value[-1] > cutoff
                }
            return True


class _RequestBodyTooLarge(Exception):
    """Internal signal used to stop reading an oversized streaming request."""


def _is_help_request_scope(scope: Scope) -> bool:
    return scope.get("type") == "http" and str(scope.get("path", "")).startswith(
        HELP_REQUEST_PATH_PREFIX
    )


def _content_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key.lower() != b"content-length":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _is_submission_scope(scope: Scope) -> bool:
    return scope.get("method") == "POST" and scope.get("path") == HELP_REQUEST_PATH_PREFIX


def _append_header_if_missing(headers: list[tuple[bytes, bytes]], key: bytes, value: bytes) -> None:
    if not any(existing_key.lower() == key for existing_key, _ in headers):
        headers.append((key, value))


async def _send_too_large(send: Send) -> None:
    payload = json.dumps(
        {
            "detail": {
                "code": "request_body_too_large",
                "message": "request body exceeds the allowed limit",
            }
        },
        separators=(",", ":"),
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"cache-control", b"no-store"),
                (b"pragma", b"no-cache"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


async def _send_rate_limited(send: Send) -> None:
    payload = json.dumps(
        {"detail": "too many help requests; please retry later"},
        separators=(",", ":"),
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"retry-after", b"60"),
                (b"cache-control", b"no-store"),
                (b"pragma", b"no-cache"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
