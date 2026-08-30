"""ASGI guards for privacy-sensitive help-request HTTP boundaries."""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HELP_REQUEST_PATH_PREFIX = "/api/v1/help-requests"
MAX_HELP_REQUEST_BODY_BYTES = 12 * 1024 * 1024


class HelpRequestSecurityMiddleware:
    """Limit request bytes and add no-store headers before FastAPI parsing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int = MAX_HELP_REQUEST_BODY_BYTES,
    ) -> None:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_help_request_scope(scope):
            await self.app(scope, receive, send)
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
