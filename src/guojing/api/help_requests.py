"""HTTP adapter for explicit, transient screenshot help submissions."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.models import HelpRequestReceipt
from guojing.application.help_requests.service import (
    HelpRequestNotFound,
    HelpRequestService,
    InvalidHelpRequestPayload,
)
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestGuidanceStep,
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)

router = APIRouter(prefix="/api/v1/help-requests", tags=["screenshot help"])


class HelpRequestGuidanceStepResponse(BaseModel):
    """A manual instruction with no executable node action or gesture."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    title: str
    instruction: str
    requires_manual_action: Literal[True]

    @classmethod
    def from_domain(cls, value: HelpRequestGuidanceStep) -> "HelpRequestGuidanceStepResponse":
        return cls(
            step_id=value.step_id,
            title=value.title,
            instruction=value.instruction,
            requires_manual_action=True,
        )


class HelpRequestGuidanceResponse(BaseModel):
    """Bounded explanatory guidance that still requires user operation."""

    model_config = ConfigDict(extra="forbid")

    title: str
    steps: list[HelpRequestGuidanceStepResponse]

    @classmethod
    def from_domain(cls, value: HelpRequestGuidance) -> "HelpRequestGuidanceResponse":
        return cls(
            title=value.title,
            steps=[HelpRequestGuidanceStepResponse.from_domain(step) for step in value.steps],
        )


class HelpRequestResultResponse(BaseModel):
    """Status projection that never contains the submitted screenshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.1"] = "1.1"
    request_id: UUID
    client_request_id: UUID
    intent: HelpRequestIntent
    processing_route: HelpRequestProcessingRoute
    processing_status: HelpRequestProcessingStatus
    received_at: datetime
    updated_at: datetime
    guidance: HelpRequestGuidanceResponse | None = None
    human_review_reason: str | None = None

    @classmethod
    def from_domain(cls, value: HelpRequestResult) -> "HelpRequestResultResponse":
        return cls(
            request_id=value.request_id,
            client_request_id=value.client_request_id,
            intent=value.intent,
            processing_route=value.processing_route,
            processing_status=value.processing_status,
            received_at=value.received_at,
            updated_at=value.updated_at,
            guidance=(
                HelpRequestGuidanceResponse.from_domain(value.guidance)
                if value.guidance is not None
                else None
            ),
            human_review_reason=value.human_review_reason,
        )


class HelpRequestResponse(HelpRequestResultResponse):
    """Submission receipt plus the status endpoint for later polling."""

    model_config = ConfigDict(extra="forbid")

    image_disposition: Literal["discarded_after_validation"]
    status_endpoint: str

    @classmethod
    def from_application(
        cls,
        value: HelpRequestReceipt,
        *,
        status_endpoint: str,
    ) -> "HelpRequestResponse":
        return cls(
            request_id=value.request_id,
            client_request_id=value.client_request_id,
            intent=value.intent,
            processing_route=value.processing_route,
            processing_status=value.processing_status,
            received_at=value.received_at,
            updated_at=value.received_at,
            image_disposition="discarded_after_validation",
            status_endpoint=status_endpoint,
        )


def _service(request: Request) -> HelpRequestService:
    """Typed dependency adapter installed by the composition root."""
    return cast(HelpRequestService, request.app.state.help_request_service)


HelpRequestServiceDependency = Annotated[HelpRequestService, Depends(_service)]


@router.post(
    "",
    response_model=HelpRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_help_request(
    request: HelpRequestRequest,
    response: Response,
    service: HelpRequestServiceDependency,
) -> HelpRequestResponse:
    """Accept only a locally sanitized image and discard its bytes after validation."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        receipt = service.accept(request)
        return HelpRequestResponse.from_application(
            receipt,
            status_endpoint=f"/api/v1/help-requests/{receipt.request_id}",
        )
    except InvalidHelpRequestPayload as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get(
    "/{request_id}",
    response_model=HelpRequestResultResponse,
)
def get_help_request_result(
    request_id: UUID,
    response: Response,
    service: HelpRequestServiceDependency,
) -> HelpRequestResultResponse:
    """Return status metadata without reopening or retaining the image."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        return HelpRequestResultResponse.from_domain(service.get_result(request_id))
    except HelpRequestNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="help request result was not found",
        ) from error
