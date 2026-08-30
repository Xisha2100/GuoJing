"""Privacy-preserving FastAPI validation error handlers."""

from typing import Any

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from guojing.api.middleware import HELP_REQUEST_PATH_PREFIX


async def handle_request_validation_error(
    request: Request,
    exc: Exception,
) -> Response:
    """Never echo parsed request values for help-request validation failures."""
    if not isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error"},
        )
    if not request.url.path.startswith(HELP_REQUEST_PATH_PREFIX):
        return await request_validation_exception_handler(request, exc)
    issues = [_safe_issue(error) for error in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "invalid_help_request",
                "message": "request validation failed",
                "issues": issues,
            }
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _safe_issue(error: dict[str, Any]) -> dict[str, object]:
    location = tuple(part for part in error.get("loc", ()) if isinstance(part, (str, int)))
    error_type = error.get("type")
    code = error_type if isinstance(error_type, str) else "validation_error"
    return {
        "code": code,
        "loc": location,
        "message": _safe_message(code),
    }


def _safe_message(code: str) -> str:
    messages = {
        "missing": "required field is missing",
        "extra_forbidden": "unknown field is not allowed",
        "string_too_long": "field is too long",
        "string_too_short": "field is too short",
        "bytes_too_long": "field is too large",
    }
    return messages.get(code, "field is invalid")
