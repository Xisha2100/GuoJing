"""LangGraph-compatible, dependency-injected help-request workflow.

The graph is intentionally implemented with plain Python first. This keeps the
state transitions deterministic and testable without a model, while the node
boundaries map directly to a future LangGraph/Deep Agent graph.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from guojing.application.help_requests.evidence_service import HelpRequestEvidenceService
from guojing.application.help_requests.processor import HelpRequestProcessor
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.tutorials.execution_plan import TutorialExecutionPlanService
from guojing.application.tutorials.matcher import (
    TutorialMatchDecision,
    TutorialMatchService,
    TutorialMatchStatus,
)
from guojing.domain.help_requests import (
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
    HelpRequestTutorialMatch,
)


class HelpRequestWorkflowStage(StrEnum):
    """Stable checkpoints a graph runner can persist or resume from."""

    RECEIVED = "received"
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
        execution_plan_service: TutorialExecutionPlanService,
        general_guidance_processor: HelpRequestProcessor,
        clock: Callable[[], datetime] | None = None,
        processing_timeout: timedelta = timedelta(minutes=2),
    ) -> None:
        if processing_timeout <= timedelta(0):
            raise ValueError("processing_timeout must be positive")
        self._help_requests = help_request_service
        self._evidence = evidence_service
        self._tutorial_matcher = tutorial_match_service
        self._execution_plan_service = execution_plan_service
        self._general_guidance_processor = general_guidance_processor
        self._clock = clock or help_request_service.current_time
        self._processing_timeout = processing_timeout

    def run(self, request_id: UUID) -> HelpRequestWorkflowState:
        """Execute one pass and convert unexpected failures into review."""
        current = self._help_requests.get_result(request_id)
        try:
            return self._run_current(current)
        except Exception:
            latest = self._help_requests.get_result(request_id)
            if latest.processing_status is HelpRequestProcessingStatus.RECEIVED:
                latest = self._help_requests.mark_processing(
                    request_id,
                    workflow_stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW.value,
                )
            if latest.processing_status is HelpRequestProcessingStatus.PROCESSING:
                result = self._help_requests.mark_needs_human_review(
                    request_id,
                    "处理过程异常, 已转人工复核.",
                    workflow_stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW.value,
                )
                return HelpRequestWorkflowState(
                    request_id=request_id,
                    result=result,
                    stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW,
                )
            raise

    def _run_current(self, current: HelpRequestResult) -> HelpRequestWorkflowState:
        """Execute one bounded pass; no node performs an Android action."""
        request_id = current.request_id
        if current.processing_status is HelpRequestProcessingStatus.GUIDANCE_READY:
            return self._state_from_result(current)
        if current.processing_status is HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW:
            return self._state_from_result(current)
        if (
            current.processing_route is HelpRequestProcessingRoute.GENERAL_GUIDANCE
            and current.processing_status is HelpRequestProcessingStatus.RECEIVED
        ):
            result = self._help_requests.process(
                request_id,
                self._general_guidance_processor,
                workflow_stage=HelpRequestWorkflowStage.COMPLETED.value,
            )
            return HelpRequestWorkflowState(
                request_id=request_id,
                result=result,
                stage=HelpRequestWorkflowStage.COMPLETED,
            )

        if (
            current.processing_route is HelpRequestProcessingRoute.GENERAL_GUIDANCE
            and current.processing_status is HelpRequestProcessingStatus.PROCESSING
        ):
            if current.updated_at <= self._clock() - self._processing_timeout:
                result = self._help_requests.mark_needs_human_review(
                    request_id,
                    "处理租约已过期, 已转人工复核.",
                    workflow_stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW.value,
                )
                return HelpRequestWorkflowState(
                    request_id=request_id,
                    result=result,
                    stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW,
                )
            return self._state_from_result(current)

        if current.processing_route is not HelpRequestProcessingRoute.TUTORIAL_MATCH:
            raise ValueError("workflow cannot resume this request state")
        if current.processing_status is HelpRequestProcessingStatus.RECEIVED:
            processing = self._help_requests.mark_processing(
                request_id,
                workflow_stage=HelpRequestWorkflowStage.AWAITING_EVIDENCE.value,
            )
        elif current.processing_status is HelpRequestProcessingStatus.PROCESSING:
            processing = current
        else:
            raise ValueError("workflow can only run tutorial requests in progress")
        envelope = self._evidence.get_latest(request_id)
        if envelope is None:
            if current.processing_status is HelpRequestProcessingStatus.PROCESSING and (
                current.updated_at <= self._clock() - self._processing_timeout
            ):
                result = self._help_requests.mark_needs_human_review(
                    request_id,
                    "等待页面证据超时, 已转人工复核.",
                    workflow_stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW.value,
                )
                return HelpRequestWorkflowState(
                    request_id=request_id,
                    result=result,
                    stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW,
                )
            return HelpRequestWorkflowState(
                request_id=request_id,
                result=processing,
                stage=HelpRequestWorkflowStage.AWAITING_EVIDENCE,
            )

        decision = self._tutorial_matcher.select(envelope)
        tutorial_match = _to_persisted_match(decision)
        if decision.status is TutorialMatchStatus.MATCHED:
            assert decision.candidate is not None
            tutorial_plan = self._execution_plan_service.build(decision.candidate)
            result = self._help_requests.mark_needs_human_review(
                request_id,
                "教程页面已匹配,请人工确认版本和步骤后发布安全说明。",
                workflow_stage=HelpRequestWorkflowStage.TUTORIAL_MATCHED.value,
                tutorial_match=tutorial_match,
                tutorial_plan=tutorial_plan,
            )
            return HelpRequestWorkflowState(
                request_id=request_id,
                result=result,
                stage=HelpRequestWorkflowStage.TUTORIAL_MATCHED,
                tutorial_decision=decision,
            )

        result = self._help_requests.mark_needs_human_review(
            request_id,
            f"教程匹配未通过安全门槛: {decision.reason.value}.",
            workflow_stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW.value,
            tutorial_match=tutorial_match,
        )
        return HelpRequestWorkflowState(
            request_id=request_id,
            result=result,
            stage=HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW,
            tutorial_decision=decision,
        )

    def inspect(self, request_id: UUID) -> HelpRequestWorkflowState:
        """Read the persisted checkpoint without starting another processing pass."""
        return self._state_from_result(self._help_requests.get_result(request_id))

    @staticmethod
    def _state_from_result(result: HelpRequestResult) -> HelpRequestWorkflowState:
        if result.workflow_stage is not None:
            try:
                stage = HelpRequestWorkflowStage(result.workflow_stage)
            except ValueError:
                stage = HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW
        elif result.processing_status is HelpRequestProcessingStatus.GUIDANCE_READY:
            stage = HelpRequestWorkflowStage.COMPLETED
        elif result.processing_route is HelpRequestProcessingRoute.TUTORIAL_MATCH:
            stage = (
                HelpRequestWorkflowStage.RECEIVED
                if result.processing_status is HelpRequestProcessingStatus.RECEIVED
                else (
                    HelpRequestWorkflowStage.AWAITING_EVIDENCE
                    if result.processing_status is HelpRequestProcessingStatus.PROCESSING
                    else HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW
                )
            )
        elif result.processing_status is HelpRequestProcessingStatus.RECEIVED:
            stage = HelpRequestWorkflowStage.RECEIVED
        else:
            stage = HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW
        return HelpRequestWorkflowState(
            request_id=result.request_id,
            result=result,
            stage=stage,
        )


def _to_persisted_match(decision: TutorialMatchDecision) -> HelpRequestTutorialMatch:
    candidate = decision.candidate
    return HelpRequestTutorialMatch(
        status=decision.status.value,
        reason=decision.reason.value,
        graph_id=candidate.graph_id if candidate is not None else None,
        node_id=candidate.node_id if candidate is not None else None,
        revision_number=candidate.revision_number if candidate is not None else None,
    )
