"""Process health endpoint."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    """Stable response contract for the process health probe."""

    status: Literal["ok"] = "ok"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check whether the API process can respond",
)
async def get_health() -> HealthResponse:
    """Return process liveness without calling external dependencies."""
    return HealthResponse()


@router.get("/ready")
async def get_ready(request: Request) -> JSONResponse:
    ready = await request.app.state.is_ready()
    return JSONResponse(
        {"status": "ready" if ready else "unavailable"},
        status_code=200 if ready else 503,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/internal/status", include_in_schema=False)
async def internal_status(request: Request) -> JSONResponse:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=404)
    coordinator = request.app.state.agent_coordinator
    return JSONResponse(
        {
            "dependencies_ready": await request.app.state.dependencies_ready(),
            "accepting": request.app.state.device_access.accepting(),
            "queue_depth": coordinator.queue_depth,
            "active_count": coordinator.active_count,
            "completed": coordinator.completed_count,
            "failed": coordinator.failed_count,
            "consecutive_failures": coordinator.consecutive_failures,
            "model_calls": coordinator.model_calls,
            "input_tokens": coordinator.input_tokens,
            "output_tokens": coordinator.output_tokens,
            "last_duration_ms": coordinator.last_duration_ms,
        },
        headers={"Cache-Control": "no-store"},
    )
