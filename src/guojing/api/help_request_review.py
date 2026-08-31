"""Authenticated reviewer endpoints for safe help-request guidance."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from guojing.api.dependencies import (
    get_admin_auth_service,
    get_help_request_service,
    get_help_request_workflow,
    require_admin,
    require_admin_session,
)
from guojing.api.help_requests import HelpRequestResultResponse
from guojing.application.auth.service import AdminAuthService
from guojing.application.help_requests.queue import HelpRequestQueue
from guojing.application.help_requests.service import HelpRequestNotFound, HelpRequestService
from guojing.application.help_requests.workflow import (
    HelpRequestWorkflow,
    HelpRequestWorkflowStage,
)
from guojing.domain.auth import AuthenticatedAdminSession
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestGuidanceStep,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)

router = APIRouter(prefix="/api/v1/admin/help-requests", tags=["help request review"])
AdminMutationDependency = Annotated[AuthenticatedAdminSession, Depends(require_admin)]
AdminSessionDependency = Annotated[
    AuthenticatedAdminSession,
    Depends(require_admin_session),
]
HelpRequestServiceDependency = Annotated[
    HelpRequestService,
    Depends(get_help_request_service),
]
HelpRequestWorkflowDependency = Annotated[
    HelpRequestWorkflow,
    Depends(get_help_request_workflow),
]
AuthServiceDependency = Annotated[AdminAuthService, Depends(get_admin_auth_service)]


class ReviewApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GuidanceStepRequest(ReviewApiModel):
    step_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=500)

    def to_domain(self) -> HelpRequestGuidanceStep:
        return HelpRequestGuidanceStep(
            step_id=self.step_id,
            title=self.title,
            instruction=self.instruction,
        )


class GuidanceRequest(ReviewApiModel):
    title: str = Field(min_length=1, max_length=160)
    steps: list[GuidanceStepRequest] = Field(min_length=1, max_length=20)

    def to_domain(self) -> HelpRequestGuidance:
        return HelpRequestGuidance(
            title=self.title,
            steps=tuple(step.to_domain() for step in self.steps),
        )


class ReviewSummary(ReviewApiModel):
    request_id: UUID
    client_request_id: UUID
    intent: str
    processing_route: str
    processing_status: str
    received_at: datetime
    updated_at: datetime
    human_review_reason: str | None

    @classmethod
    def from_domain(cls, value: HelpRequestResult) -> "ReviewSummary":
        return cls(
            request_id=value.request_id,
            client_request_id=value.client_request_id,
            intent=value.intent.value,
            processing_route=value.processing_route.value,
            processing_status=value.processing_status.value,
            received_at=value.received_at,
            updated_at=value.updated_at,
            human_review_reason=value.human_review_reason,
        )


class ProcessNextRequest(ReviewApiModel):
    limit: int = Field(default=10, ge=1, le=100)


@router.get("/reviews", response_model=list[ReviewSummary])
def list_help_request_reviews(
    _admin: AdminSessionDependency,
    service: HelpRequestServiceDependency,
) -> list[ReviewSummary]:
    """List review metadata without exposing question text or image bytes."""
    return [
        ReviewSummary.from_domain(value)
        for value in service.list_results(
            status=HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW,
        )
    ]


@router.post("/process-next", response_model=list[HelpRequestResultResponse])
def process_next_help_requests(
    request: ProcessNextRequest,
    _admin: AdminMutationDependency,
    auth_service: AuthServiceDependency,
    workflow: HelpRequestWorkflowDependency,
    service: HelpRequestServiceDependency,
) -> list[HelpRequestResultResponse]:
    """Run one bounded worker pass from the authenticated admin boundary."""
    auth_service.record_action(
        _admin,
        "help_request.process_batch_requested",
        "help_request",
        None,
        {"limit": request.limit},
    )
    queue = HelpRequestQueue(service)
    results: list[HelpRequestResultResponse] = []
    seen: set[UUID] = set()
    for _ in range(request.limit):
        pending = queue.next_received()
        if pending is None or pending.request_id in seen:
            break
        seen.add(pending.request_id)
        results.append(
            HelpRequestResultResponse.from_workflow_state(workflow.run(pending.request_id))
        )
    return results


@router.post("/{request_id}/process", response_model=HelpRequestResultResponse)
def process_help_request(
    request_id: UUID,
    _admin: AdminMutationDependency,
    auth_service: AuthServiceDependency,
    workflow: HelpRequestWorkflowDependency,
) -> HelpRequestResultResponse:
    """Run the production workflow through the authenticated admin boundary."""
    # Help-request state and the admin audit repository do not yet share a
    # database transaction.  Write the durable operator intent first so an
    # audit outage cannot leave a successful-looking state transition with no
    # corresponding record.  The deterministic operation id lets a future
    # outbox/replay worker correlate retries without exposing request content.
    auth_service.record_action(
        _admin,
        "help_request.process_requested",
        "help_request",
        str(request_id),
        {
            "operation_id": f"help-request:{request_id}:process",
            "phase": "requested",
        },
    )
    try:
        state = workflow.run(request_id)
    except HelpRequestNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="help request not found",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return HelpRequestResultResponse.from_workflow_state(state)


@router.post(
    "/{request_id}/guidance",
    response_model=HelpRequestResultResponse,
)
def publish_reviewed_guidance(
    request_id: UUID,
    guidance: GuidanceRequest,
    admin: AdminMutationDependency,
    service: HelpRequestServiceDependency,
    auth_service: AuthServiceDependency,
) -> HelpRequestResultResponse:
    """Publish only a validated, manual, non-dangerous review result."""
    try:
        domain_guidance = guidance.to_domain()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    # See process_help_request: this is intentionally a request event rather
    # than a post-transition "published" claim until both repositories can be
    # committed atomically (or an outbox is introduced).
    auth_service.record_action(
        admin,
        "help_request.guidance_publish_requested",
        "help_request",
        str(request_id),
        {
            "operation_id": f"help-request:{request_id}:guidance-publish",
            "phase": "requested",
            "step_count": len(guidance.steps),
        },
    )
    try:
        result = service.publish_guidance(
            request_id,
            domain_guidance,
            workflow_stage=HelpRequestWorkflowStage.COMPLETED.value,
        )
    except HelpRequestNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="help request not found",
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return HelpRequestResultResponse.from_domain(result)
