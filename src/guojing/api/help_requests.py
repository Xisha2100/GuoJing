"""HTTP adapter for explicit, transient screenshot help submissions."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.models import HelpRequestReceipt
from guojing.application.help_requests.service import (
    HelpRequestService,
    InvalidHelpRequestPayload,
)
from guojing.domain.help_requests import HelpRequestIntent, HelpRequestProcessingRoute

router = APIRouter(prefix="/api/v1/help-requests", tags=["screenshot help"])


class HelpRequestResponse(BaseModel):
    """Receipt returned without retaining or echoing screenshot bytes."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    client_request_id: UUID
    intent: HelpRequestIntent
    processing_route: HelpRequestProcessingRoute
    processing_status: Literal["accepted_no_model"]
    image_disposition: Literal["discarded_after_validation"]
    received_at: datetime

    @classmethod
    def from_application(cls, value: HelpRequestReceipt) -> "HelpRequestResponse":
        return cls(
            request_id=value.request_id,
            client_request_id=value.client_request_id,
            intent=value.intent,
            processing_route=value.processing_route,
            processing_status="accepted_no_model",
            image_disposition="discarded_after_validation",
            received_at=value.received_at,
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
        return HelpRequestResponse.from_application(service.accept(request))
    except InvalidHelpRequestPayload as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
