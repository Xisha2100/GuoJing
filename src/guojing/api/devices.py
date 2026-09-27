"""One-time invitations bound to client-generated installation credentials."""

from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from guojing.application.device_access import DeviceAccessService

router = APIRouter(prefix="/api/v1/devices", tags=["device admission"])


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    invitation_code: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    installation_id: UUID
    device_secret: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ActivationResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    device_id: UUID
    status: Literal["active"] = "active"
    expires_at: str


@router.post("/activate", response_model=ActivationResponse)
async def activate(payload: ActivationRequest, request: Request) -> ActivationResponse:
    access = cast(DeviceAccessService, request.app.state.device_access)
    device = access.activate(
        payload.invitation_code, payload.installation_id, payload.device_secret
    )
    return ActivationResponse(device_id=device.device_id, expires_at=device.expires_at.isoformat())
