"""HTTP adapter for explicit, transient screenshot help submissions."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from guojing.api.dependencies import get_help_request_evidence_service, get_help_request_workflow
from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.evidence_dto import HelpRequestEvidenceRequest
from guojing.application.help_requests.evidence_service import (
    HelpRequestEvidenceService,
    InvalidHelpRequestEvidence,
)
from guojing.application.help_requests.models import HelpRequestReceipt
from guojing.application.help_requests.service import (
    HelpRequestNotFound,
    HelpRequestService,
    InvalidHelpRequestPayload,
)
from guojing.application.help_requests.workflow import HelpRequestWorkflow, HelpRequestWorkflowState
from guojing.domain.evidence import EvidenceBounds, EvidenceEnvelope
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


class TutorialMatchResponse(BaseModel):
    """Safe tutorial checkpoint metadata; never returns OCR or screenshot content."""

    model_config = ConfigDict(extra="forbid")

    status: str
    reason: str
    graph_id: str | None = None
    node_id: str | None = None
    revision_number: int | None = None

    @classmethod
    def from_state(cls, state: HelpRequestWorkflowState) -> "TutorialMatchResponse | None":
        decision = state.tutorial_decision
        if decision is not None:
            candidate = decision.candidate
            return cls(
                status=decision.status.value,
                reason=decision.reason.value,
                graph_id=candidate.graph_id if candidate is not None else None,
                node_id=candidate.node_id if candidate is not None else None,
                revision_number=candidate.revision_number if candidate is not None else None,
            )
        match = state.result.tutorial_match
        if match is None:
            return None
        return cls(
            status=match.status,
            reason=match.reason,
            graph_id=match.graph_id,
            node_id=match.node_id,
            revision_number=match.revision_number,
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
    workflow_stage: str | None = None
    tutorial_match: TutorialMatchResponse | None = None

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
            workflow_stage=value.workflow_stage,
            tutorial_match=(
                TutorialMatchResponse(
                    status=value.tutorial_match.status,
                    reason=value.tutorial_match.reason,
                    graph_id=value.tutorial_match.graph_id,
                    node_id=value.tutorial_match.node_id,
                    revision_number=value.tutorial_match.revision_number,
                )
                if value.tutorial_match is not None
                else None
            ),
        )

    @classmethod
    def from_workflow_state(cls, state: HelpRequestWorkflowState) -> "HelpRequestResultResponse":
        result = cls.from_domain(state.result)
        payload = result.model_dump()
        payload["workflow_stage"] = state.stage.value
        payload["tutorial_match"] = TutorialMatchResponse.from_state(state)
        return cls(**payload)


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
            workflow_stage="received",
            image_disposition="discarded_after_validation",
            status_endpoint=status_endpoint,
        )


def _service(request: Request) -> HelpRequestService:
    """Typed dependency adapter installed by the composition root."""
    return cast(HelpRequestService, request.app.state.help_request_service)


HelpRequestServiceDependency = Annotated[HelpRequestService, Depends(_service)]
HelpRequestEvidenceServiceDependency = Annotated[
    HelpRequestEvidenceService,
    Depends(get_help_request_evidence_service),
]
HelpRequestWorkflowDependency = Annotated[
    HelpRequestWorkflow,
    Depends(get_help_request_workflow),
]


class EvidenceBoundsResponse(BaseModel):
    """Normalized placement metadata without screen text or pixels."""

    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    @classmethod
    def from_domain(cls, value: EvidenceBounds) -> "EvidenceBoundsResponse":
        return cls(
            left=value.left,
            top=value.top,
            right=value.right,
            bottom=value.bottom,
        )


class EvidenceAnchorResponse(BaseModel):
    """Anchor confidence that is safe to display to a reviewer."""

    model_config = ConfigDict(extra="forbid")

    anchor_id: str
    confidence: float
    normalized_bounds: EvidenceBoundsResponse | None = None


class HelpRequestEvidenceResponse(BaseModel):
    """Stored evidence projection; intentionally excludes OCR text and image bytes."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    evidence_id: UUID
    request_id: UUID
    package_name: str
    version_name: str
    version_code: int
    source: str
    sharing_policy: str
    structure_score: float
    captured_at: datetime
    expires_at: datetime
    anchors: list[EvidenceAnchorResponse]

    @classmethod
    def from_domain(cls, value: EvidenceEnvelope) -> "HelpRequestEvidenceResponse":
        return cls(
            evidence_id=value.evidence_id,
            request_id=value.request_id,
            package_name=value.package_name,
            version_name=value.version_name,
            version_code=value.version_code,
            source=value.source.value,
            sharing_policy=value.sharing_policy.value,
            structure_score=value.structure_score,
            captured_at=value.captured_at,
            expires_at=value.expires_at,
            anchors=[
                EvidenceAnchorResponse(
                    anchor_id=anchor.anchor_id,
                    confidence=anchor.confidence,
                    normalized_bounds=(
                        EvidenceBoundsResponse.from_domain(anchor.normalized_bounds)
                        if anchor.normalized_bounds is not None
                        else None
                    ),
                )
                for anchor in value.anchors
            ],
        )


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


@router.post(
    "/{request_id}/evidence",
    response_model=HelpRequestEvidenceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_help_request_evidence(
    request_id: UUID,
    evidence: HelpRequestEvidenceRequest,
    response: Response,
    service: HelpRequestEvidenceServiceDependency,
) -> HelpRequestEvidenceResponse:
    """Accept normalized evidence only after an explicit sanitized network decision."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        envelope = service.record(request_id, evidence.to_domain(request_id))
    except (InvalidHelpRequestEvidence, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    return HelpRequestEvidenceResponse.from_domain(envelope)


@router.get(
    "/{request_id}/evidence/latest",
    response_model=HelpRequestEvidenceResponse,
)
def get_latest_help_request_evidence(
    request_id: UUID,
    response: Response,
    service: HelpRequestEvidenceServiceDependency,
) -> HelpRequestEvidenceResponse:
    """Return only the newest unexpired semantic envelope."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    envelope = service.get_latest(request_id)
    if envelope is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="help request evidence was not found",
        )
    return HelpRequestEvidenceResponse.from_domain(envelope)


@router.get(
    "/{request_id}",
    response_model=HelpRequestResultResponse,
)
def get_help_request_result(
    request_id: UUID,
    response: Response,
    workflow: HelpRequestWorkflowDependency,
) -> HelpRequestResultResponse:
    """Return status metadata without reopening or retaining the image."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        return HelpRequestResultResponse.from_workflow_state(workflow.inspect(request_id))
    except HelpRequestNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="help request result was not found",
        ) from error
