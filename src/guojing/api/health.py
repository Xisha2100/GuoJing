"""Process health endpoint."""

from typing import Literal

from fastapi import APIRouter
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
