"""HTTP API for asynchronous multimodal guidance agent runs."""

import base64
import binascii
import io
import json
from collections.abc import AsyncIterator
from hashlib import sha256
from typing import Annotated, Final, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from guojing.application.agent.coordinator import AgentQueueFull, AgentRunCoordinator
from guojing.application.agent.service import (
    AgentRunNotFound,
    AgentService,
    AgentSessionClosed,
    AgentSessionConflict,
    AgentSessionNotFound,
)
from guojing.domain.agent_guidance import (
    AgentRun,
    AgentRunStatus,
    AgentSession,
    GuidanceDecision,
)

router = APIRouter(prefix="/api/v1/agent", tags=["visual guidance agent"])

SCHEMA_VERSION: Final[Literal["1.0"]] = "1.0"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
MAX_BASE64_LENGTH = ((MAX_IMAGE_BYTES + 2) // 3) * 4
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_DIMENSION * MAX_IMAGE_DIMENSION


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    client_session_id: UUID
    goal: str = Field(min_length=1, max_length=500)
    target_package: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$",
    )

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("goal must not be blank")
        return normalized


class SessionCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    session_id: UUID
    access_token: str
    status: Literal["active"] = "active"


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    client_turn_id: UUID
    image_media_type: Literal["image/jpeg", "image/png"]
    screen_width: int = Field(ge=1, le=MAX_IMAGE_DIMENSION)
    screen_height: int = Field(ge=1, le=MAX_IMAGE_DIMENSION)
    screenshot_base64: str = Field(min_length=4, max_length=MAX_BASE64_LENGTH)


class TargetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    right: float
    bottom: float


class GuidanceDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["continue", "completed", "cannot_determine"]
    instruction: str | None
    target: TargetResponse | None
    confidence: float

    @classmethod
    def from_domain(cls, value: GuidanceDecision) -> "GuidanceDecisionResponse":
        target = None
        if value.target is not None:
            target = TargetResponse(
                left=value.target.left,
                top=value.target.top,
                right=value.target.right,
                bottom=value.target.bottom,
            )
        return cls(
            status=value.status.value,
            instruction=value.instruction,
            target=target,
            confidence=value.confidence,
        )


class RunAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: UUID
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    events_endpoint: str


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: UUID
    session_id: UUID
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    result: GuidanceDecisionResponse | None
    error_code: str | None
    retryable: bool

    @classmethod
    def from_domain(cls, value: AgentRun) -> "RunResponse":
        return cls(
            run_id=value.run_id,
            session_id=value.session_id,
            status=value.status.value,
            result=(
                GuidanceDecisionResponse.from_domain(value.result)
                if value.result is not None
                else None
            ),
            error_code=value.error_code,
            retryable=value.retryable,
        )


AgentToken = Annotated[str | None, Header(alias="X-Agent-Session-Token")]


def _service(request: Request) -> AgentService:
    return cast(AgentService, request.app.state.agent_service)


def _coordinator(request: Request) -> AgentRunCoordinator:
    return cast(AgentRunCoordinator, request.app.state.agent_coordinator)


@router.post(
    "/sessions",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(payload: SessionCreateRequest, request: Request) -> SessionCreateResponse:
    try:
        session, token = _service(request).create_session(
            client_session_id=payload.client_session_id,
            goal=payload.goal,
            target_package=payload.target_package,
        )
    except AgentSessionConflict as error:
        raise HTTPException(status_code=409, detail="client_session_id already exists") from error
    return SessionCreateResponse(session_id=session.session_id, access_token=token)


@router.post(
    "/sessions/{session_id}/runs",
    response_model=RunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    session_id: UUID,
    payload: RunCreateRequest,
    request: Request,
    token: AgentToken = None,
) -> RunAcceptedResponse:
    service = _service(request)
    session = _require_session(service, session_id, token)
    image = _decode_and_validate_image(payload)
    digest = sha256(image).hexdigest()
    try:
        run, created = service.create_or_get_run(
            session=session,
            client_turn_id=payload.client_turn_id,
            image_sha256=digest,
            image_media_type=payload.image_media_type,
            screen_width=payload.screen_width,
            screen_height=payload.screen_height,
            model_name=request.app.state.settings.deepseek_vision_model,
        )
    except AgentSessionClosed as error:
        raise HTTPException(status_code=409, detail="agent session is not active") from error
    if not created and (
        run.image_sha256 != digest
        or run.image_media_type != payload.image_media_type
        or run.screen_width != payload.screen_width
        or run.screen_height != payload.screen_height
    ):
        raise HTTPException(status_code=409, detail="client_turn_id payload does not match")
    if not created and run.status is AgentRunStatus.FAILED and run.retryable:
        run = service.retry_run(run)
        created = True
    if created:
        try:
            await _coordinator(request).submit(run=run, session=session, screenshot=image)
        except AgentQueueFull as error:
            service.fail_run(run, "queue_full", retryable=True)
            raise HTTPException(status_code=429, detail="agent run queue is full") from error
    return RunAcceptedResponse(
        run_id=run.run_id,
        status=run.status.value,
        events_endpoint=f"/api/v1/agent/runs/{run.run_id}/events",
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: UUID, request: Request, token: AgentToken = None) -> RunResponse:
    _session, run = _require_run(_service(request), run_id, token)
    return RunResponse.from_domain(run)


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: UUID,
    request: Request,
    token: AgentToken = None,
) -> StreamingResponse:
    _require_run(_service(request), run_id, token)

    async def stream() -> AsyncIterator[str]:
        async for run in _coordinator(request).events(run_id):
            payload = RunResponse.from_domain(run).model_dump(mode="json")
            yield f"event: {run.status.value}\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: UUID,
    request: Request,
    token: AgentToken = None,
) -> Response:
    _session, run = _require_run(_service(request), run_id, token)
    await _coordinator(request).cancel(run)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_session(
    session_id: UUID,
    request: Request,
    token: AgentToken = None,
) -> Response:
    service = _service(request)
    session = _require_session(service, session_id, token)
    service.close_session(session)
    await _coordinator(request).destroy_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _require_session(
    service: AgentService,
    session_id: UUID,
    token: str | None,
) -> AgentSession:
    try:
        return service.require_session(session_id, token or "")
    except AgentSessionNotFound as error:
        raise HTTPException(status_code=404, detail="agent session was not found") from error


def _require_run(
    service: AgentService,
    run_id: UUID,
    token: str | None,
) -> tuple[AgentSession, AgentRun]:
    try:
        return service.get_authorized_run(run_id, token or "")
    except AgentRunNotFound as error:
        raise HTTPException(status_code=404, detail="agent run was not found") from error


def _decode_and_validate_image(payload: RunCreateRequest) -> bytes:
    try:
        image_bytes = base64.b64decode(payload.screenshot_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=422, detail="screenshot_base64 is invalid") from error
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="screenshot is empty or too large")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            actual_format = image.format
            actual_size = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=422, detail="screenshot is not a valid image") from error
    expected_format = "JPEG" if payload.image_media_type == "image/jpeg" else "PNG"
    if actual_format != expected_format:
        raise HTTPException(status_code=422, detail="image_media_type does not match content")
    if actual_size != (payload.screen_width, payload.screen_height):
        raise HTTPException(status_code=422, detail="screen dimensions do not match image")
    if max(actual_size) > MAX_IMAGE_DIMENSION:
        raise HTTPException(status_code=422, detail="screenshot dimensions are too large")
    return image_bytes
