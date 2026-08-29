"""LangGraph-compatible, dependency-injected help-request workflow.

The graph is intentionally implemented with plain Python first. This keeps the
state transitions deterministic and testable without a model, while the node
boundaries map directly to a future LangGraph/Deep Agent graph.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from guojing.application.help_requests.evidence_service import HelpRequestEvidenceService
from guojing.application.help_requests.processor import HelpRequestProcessor
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.tutorials.matcher import (
    TutorialMatchDecision,
    TutorialMatchService,
    TutorialMatchStatus,
)
from guojing.domain.help_requests import (
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
)


class HelpRequestWorkflowStage(StrEnum):
    """Stable checkpoints a graph runner can persist or resume from."""

    COMPLETED = "completed"
    AWAITING_EVIDENCE = "awaiting_evidence"
    TUTORIAL_MATCHED = "tutorial_matched"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass(frozen=True, slots=True)
class HelpRequestWorkflowState:
    """Serializable-looking graph state with no raw screenshot content."""

    request_id: UUID
    result: HelpRequestResult
    stage: HelpRequestWorkflowStage
    tutorial_decision: TutorialMatchDecision | None = None


class HelpRequestWorkflow:
    """Orchestrate deterministic nodes without allowing UI or agents to mutate state."""

    def __init__(
        self,
        help_request_service: HelpRequestService,
        evidence_service: HelpRequestEvidenceService,
        tutorial_match_service: TutorialMatchService,
        general_guidance_processor: HelpRequestProcessor,
    ) -> None:
        self._help_requests = help_request_service
        self._evidence = evidence_service
        self._tutorial_matcher = tutorial_match_service
        self._general_guidance_processor = general_guidance_processor

    def run(self, request_id: UUID) -> HelpRequestWorkflowState:
        """Execute one bounded pass; no node performs an Android action."""
        current = self._help_requests.get_result(request_id)
        if (
            current.processing_route is HelpRequestProcessingRoute.GENERAL_GUIDANCE
            and current.processing_status is HelpRequestProcessingStatus.RECEIVED
        ):
            result = self._help_requests.process(
                request_id,
                self._general_guidance_processor,
            )
            return HelpRequestWorkflowState(
                request_id=request_id,
                result=result,
                stage=HelpRequestWorkflowStage.COMPLETED,
            )

        if current.processing_route is not HelpRequestProcessingRoute.TUTORIAL_MATCH:
            raise ValueError("workflow cannot resume this request state")
        if current.processing_status is HelpRequestProcessingStatus.RECEIVED:
            processing = self._help_requests.mark_processing(request_id)
        elif current.processing_status is HelpRequestProcessingStatus.PROCESSING:
            processing = current
        else:
            raise ValueError("workflow can only run tutorial requests in progress")
        envelope = self._evidence.get_latest(request_id)
        if envelope is None:
            return HelpRequestWorkflowState(
                request_id=request_id,
                result=processing,
                stage=HelpRequestWorkflowStage.AWAITING_EVIDENCE,
            )

        decision = self._tutorial_matcher.select(envelope)
        if decision.status is TutorialMatchStatus.MATCHED:
            return HelpRequestWorkflowState(
                request_id=request_id,
                result=processing,
                stage=HelpRequestWorkflowStage.TUTORIAL_MATCHED,
                tutorial_decision=decision,
            )

        result = self._help_requests.mark_needs_human_review(
            request_id,
            f"教程匹配未通过安全门槛: {decision.reason.value}.",
        )
        return HelpRequestWorkflowState(
            request_id=request_id,
            result=result,
            stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW,
            tutorial_decision=decision,
        )
