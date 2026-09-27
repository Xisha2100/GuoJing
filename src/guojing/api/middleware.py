"""Authenticate before consuming images and bound actual streamed body bytes."""

from collections import defaultdict, deque
from time import monotonic
from typing import cast

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from guojing.application.device_access import DeviceAccessService
from guojing.domain.device_access import AccessDenied

AGENT_PATH_PREFIX = "/api/v1/agent/"
DEVICE_PATH_PREFIX = "/api/v1/devices/"
MAX_AGENT_REQUEST_BYTES = 12 * 1024 * 1024


class _BodyTooLarge(Exception):
    pass


class SlidingRateLimit:
    def __init__(self) -> None:
        self._entries: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int) -> None:
        now = monotonic()
        for old_key in list(self._entries):
            values = self._entries[old_key]
            while values and values[0] <= now - 60:
                values.popleft()
            if not values:
                del self._entries[old_key]
        if key not in self._entries and len(self._entries) >= 10_000:
            raise AccessDenied("rate_limited", 429, 60)
        values = self._entries[key]
        if len(values) >= limit:
            raise AccessDenied("rate_limited", 429, max(1, int(60 - now + values[0])))
        values.append(now)


def access_response(error: AccessDenied) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    return JSONResponse(
        status_code=error.status,
        content={"detail": {"code": error.code, "message": "request cannot be accepted"}},
        headers=headers,
    )


class AgentSecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._rates = SlidingRateLimit()
        self._body_readers = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if scope["type"] != "http" or not path.startswith((AGENT_PATH_PREFIX, DEVICE_PATH_PREFIX)):
            await self._app(scope, receive, send)
            return
        headers = MutableHeaders(scope=scope)
        is_agent = path.startswith(AGENT_PATH_PREFIX)
        maximum = MAX_AGENT_REQUEST_BYTES if is_agent else 16 * 1024
        try:
            if is_agent:
                access = cast(DeviceAccessService, scope["app"].state.device_access)
                identity = access.authenticate(headers.get("authorization", ""))
                scope.setdefault("state", {})["device"] = identity
                if scope["method"] == "POST" and path.endswith("/runs"):
                    self._rates.check(f"run:{identity.device_id}", 6)
            else:
                client = scope.get("client")
                self._rates.check(f"activate:{client[0] if client else 'unknown'}", 5)
            raw_length = headers.get("content-length")
            if raw_length is not None:
                try:
                    length = int(raw_length)
                except ValueError as error:
                    raise AccessDenied("invalid_content_length", 400) from error
                if length < 0:
                    raise AccessDenied("invalid_content_length", 400)
                if length > maximum:
                    raise AccessDenied("request_too_large", 413)
            if self._body_readers >= 4 and scope["method"] == "POST":
                raise AccessDenied("service_busy", 503, 5)
        except AccessDenied as error:
            await access_response(error)(scope, receive, send)
            return

        size = 0
        too_large = False
        response_started = False

        async def bounded_receive() -> Message:
            nonlocal size, too_large
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > maximum:
                    too_large = True
                    raise _BodyTooLarge
            return message

        async def secure_send(message: Message) -> None:
            nonlocal response_started
            # FastAPI may translate a receive exception to 400. Replace it with 413.
            if too_large:
                return
            if message["type"] == "http.response.start":
                response_started = True
                response_headers = MutableHeaders(scope=message)
                response_headers["Cache-Control"] = "no-store"
                response_headers["Pragma"] = "no-cache"
                response_headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        counted = scope["method"] == "POST"
        if counted:
            self._body_readers += 1
        try:
            try:
                await self._app(scope, bounded_receive, secure_send)
            except _BodyTooLarge:
                pass
            if too_large and not response_started:
                await access_response(AccessDenied("request_too_large", 413))(scope, receive, send)
        finally:
            if counted:
                self._body_readers -= 1
