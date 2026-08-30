"""Tests for the dependency-injected help-request workflow graph."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import NoReturn
from uuid import UUID, uuid4

from guojing.application.help_requests.basic_guidance import DeterministicHelpRequestProcessor
from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.evidence_service import HelpRequestEvidenceService
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.help_requests.workflow import (
    HelpRequestWorkflow,
    HelpRequestWorkflowStage,
)
from guojing.application.tutorials.matcher import TutorialMatchService
from guojing.application.tutorials.models import PublishedTutorial, PublishedTutorialSummary
from guojing.application.tutorials.service import TutorialService
from guojing.domain.evidence import (
    EvidenceAnchor,
    EvidenceEnvelope,
    EvidenceSharingPolicy,
    EvidenceSource,
)
from guojing.domain.tutorials.models import (
    AnchorRole,
    AppIdentity,
    PrivacyMode,
    ScreenAnchor,
    SemanticLocator,
    TutorialGraph,
    TutorialNode,
    VerificationStatus,
)


class StubTutorialRepository:
    def __init__(self, graph: TutorialGraph) -> None:
        self._tutorial = PublishedTutorial(
            graph=graph,
            revision_number=1,
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
        )

    def create_revision(self, graph: TutorialGraph) -> NoReturn:  # pragma: no cover
        raise NotImplementedError

    def publish_revision(self, graph_id: str, revision_number: int) -> NoReturn:  # pragma: no cover
        raise NotImplementedError

    def list_published(self) -> tuple[PublishedTutorialSummary, ...]:
        graph = self._tutorial.graph
        return (
            PublishedTutorialSummary(
                graph_id=graph.graph_id,
                title=graph.title,
                package_name=graph.recorded_app.package_name,
                recorded_version_name=graph.recorded_app.version_name,
                recorded_version_code=graph.recorded_app.version_code,
                revision_number=self._tutorial.revision_number,
                published_at=self._tutorial.published_at,
            ),
        )

    def get_published(self, graph_id: str) -> PublishedTutorial:
        assert graph_id == self._tutorial.graph.graph_id
        return self._tutorial


def _graph() -> TutorialGraph:
    app = AppIdentity("com.tencent.mm", "8.0.60", 2_600)
    node = TutorialNode(
        node_id="chat_list",
        title="微信聊天列表",
        anchors=(
            ScreenAnchor(
                anchor_id="chat_tab",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(resource_id="com.tencent.mm:id/chat_tab"),
            ),
        ),
        privacy_mode=PrivacyMode.LOCAL_ONLY,
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=2_600,
    )
    return TutorialGraph(
        graph_id="wechat_chat_list",
        title="打开微信聊天列表",
        recorded_app=app,
        start_node_id=node.node_id,
        nodes=(node,),
        transitions=(),
    )


def _request(intent: str = "recorded_tutorial") -> HelpRequestRequest:
    image = b"\xff\xd8\xff\xd9"
    return HelpRequestRequest(
        client_request_id=uuid4(),
        intent=intent,
        question="当前页面下一步怎么做?",
        image_media_type="image/jpeg",
        image_width=720,
        image_height=1_440,
        redaction_count=1,
        no_sensitive_content_confirmed=False,
        sanitized_sha256=sha256(image).hexdigest(),
        send_consent=True,
        sanitized_image_base64="/9j/2Q==",
    )


def _evidence(request_id: UUID, *, confidence: float = 1.0) -> EvidenceEnvelope:
    captured = datetime.now(UTC)
    return EvidenceEnvelope(
        evidence_id=uuid4(),
        request_id=request_id,
        package_name="com.tencent.mm",
        version_name="8.0.60",
        version_code=2_600,
        source=EvidenceSource.ACCESSIBILITY,
        sharing_policy=EvidenceSharingPolicy.SANITIZED_NETWORK_ALLOWED,
        structure_score=confidence,
        captured_at=captured,
        expires_at=captured + timedelta(minutes=10),
        anchors=(EvidenceAnchor("chat_tab", confidence),),
    )


def _workflow(
    help_service: HelpRequestService,
) -> tuple[HelpRequestWorkflow, HelpRequestEvidenceService]:
    evidence_service = HelpRequestEvidenceService(help_service)
    tutorial_service = TutorialMatchService(TutorialService(StubTutorialRepository(_graph())))
    return (
        HelpRequestWorkflow(
            help_service,
            evidence_service,
            tutorial_service,
            DeterministicHelpRequestProcessor(),
        ),
        evidence_service,
    )


def test_tutorial_request_waits_for_evidence_then_selects_tutorial() -> None:
    help_service = HelpRequestService()
    receipt = help_service.accept(_request())
    workflow, evidence_service = _workflow(help_service)

    waiting = workflow.run(receipt.request_id)

    assert waiting.stage is HelpRequestWorkflowStage.AWAITING_EVIDENCE
    assert waiting.result.processing_status.value == "processing"

    evidence_service.record(receipt.request_id, _evidence(receipt.request_id))
    matched = workflow.run(receipt.request_id)

    assert matched.stage is HelpRequestWorkflowStage.TUTORIAL_MATCHED
    assert matched.result.processing_status.value == "needs_human_review"
    assert matched.tutorial_decision is not None
    assert matched.tutorial_decision.candidate is not None
    assert matched.tutorial_decision.candidate.node_id == "chat_list"


def test_uncertain_tutorial_evidence_is_sent_to_human_review() -> None:
    help_service = HelpRequestService()
    receipt = help_service.accept(_request())
    workflow, evidence_service = _workflow(help_service)
    evidence_service.record(receipt.request_id, _evidence(receipt.request_id, confidence=0.5))

    state = workflow.run(receipt.request_id)

    assert state.stage is HelpRequestWorkflowStage.NEEDS_HUMAN_REVIEW
    assert state.result.human_review_reason is not None


def test_general_guidance_completes_through_processor() -> None:
    help_service = HelpRequestService()
    receipt = help_service.accept(_request("general_guidance"))

    workflow, _ = _workflow(help_service)
    state = workflow.run(receipt.request_id)

    assert state.stage is HelpRequestWorkflowStage.COMPLETED
    assert state.result.guidance is not None


def test_workflow_replays_terminal_request_without_restarting_it() -> None:
    help_service = HelpRequestService()
    receipt = help_service.accept(_request("general_guidance"))
    workflow, _ = _workflow(help_service)
    workflow.run(receipt.request_id)

    replayed = workflow.run(receipt.request_id)

    assert replayed.stage is HelpRequestWorkflowStage.COMPLETED
    assert replayed.result.guidance is not None
