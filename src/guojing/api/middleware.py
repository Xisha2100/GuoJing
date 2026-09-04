"""Transport limits and no-store headers for agent payloads."""

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

AGENT_PATH_PREFIX = "/api/v1/agent/"
MAX_AGENT_REQUEST_BYTES = 12 * 1024 * 1024


class AgentSecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith(AGENT_PATH_PREFIX):
            await self._app(scope, receive, send)
            return
        headers = MutableHeaders(scope=scope)
        raw_length = headers.get("content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > MAX_AGENT_REQUEST_BYTES:
                    await JSONResponse(
                        status_code=413,
                        content={"detail": "request body is too large"},
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
                    )(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse(
                    status_code=400,
                    content={"detail": "invalid content-length"},
                    headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
                )(scope, receive, send)
                return

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["Cache-Control"] = "no-store"
                response_headers["Pragma"] = "no-cache"
                response_headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        await self._app(scope, receive, secure_send)
