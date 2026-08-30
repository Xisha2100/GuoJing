"""Pinned, risk-filtered plan construction from a matched tutorial node."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import NoReturn

from guojing.application.tutorials.execution_plan import TutorialExecutionPlanService
from guojing.application.tutorials.matcher import TutorialMatchCandidate
from guojing.application.tutorials.models import PublishedTutorial, PublishedTutorialSummary
from guojing.application.tutorials.service import TutorialService
from guojing.domain.tutorials.compatibility import ReuseAssessment, ReuseReason
from guojing.domain.tutorials.matching import ScreenMatchResult, ScreenMatchStatus
from guojing.domain.tutorials.models import (
    ActionKind,
    AnchorRole,
    AppIdentity,
    PrivacyMode,
    RiskLevel,
    ScreenAnchor,
    SemanticLocator,
    TutorialGraph,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)


class StubTutorialRepository:
    def __init__(self, tutorial: PublishedTutorial) -> None:
        self._tutorial = tutorial

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


def _graph() -> tuple[TutorialGraph, TutorialTransition]:
    app = AppIdentity("com.tencent.mm", "8.0.60", 2_600)
    chat_list = TutorialNode(
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
    conversation = TutorialNode(
        node_id="conversation",
        title="家人聊天页",
        anchors=(
            ScreenAnchor(
                anchor_id="chat_title",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(text="家人"),
            ),
        ),
        privacy_mode=PrivacyMode.LOCAL_ONLY,
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=2_600,
    )
    low_risk = TutorialTransition(
        transition_id="open_family_chat",
        source_node_id=chat_list.node_id,
        target_node_id=conversation.node_id,
        action_kind=ActionKind.TAP,
        instruction="点击“家人”聊天",
        risk_level=RiskLevel.LOW,
        target_anchor_id="chat_title",
    )
    return (
        TutorialGraph(
            graph_id="wechat_open_family_chat",
            title="打开家人微信聊天",
            recorded_app=app,
            start_node_id=chat_list.node_id,
            nodes=(chat_list, conversation),
            transitions=(low_risk,),
        ),
        low_risk,
    )


def test_plan_pins_revision_and_filters_financial_transition() -> None:
    tutorial_graph, open_chat_transition = _graph()
    financial = replace(
        open_chat_transition,
        transition_id="send_money",
        risk_level=RiskLevel.FINANCIAL,
    )
    graph = replace(tutorial_graph, transitions=(open_chat_transition, financial))
    tutorial = PublishedTutorial(
        graph=graph,
        revision_number=1,
        published_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    candidate = TutorialMatchCandidate(
        graph_id=graph.graph_id,
        node_id=open_chat_transition.source_node_id,
        revision_number=tutorial.revision_number,
        screen_match=ScreenMatchResult(
            status=ScreenMatchStatus.MATCHED,
            score=1.0,
            matched_required=(),
            missing_required=(),
            matched_optional=(),
            matched_forbidden=(),
            reasons=(),
        ),
        reuse_assessment=ReuseAssessment(
            status=VerificationStatus.VERIFIED,
            can_attempt_transition=True,
            requires_admin_review=False,
            reason=ReuseReason.SAME_VERIFIED_VERSION,
        ),
    )

    plan = TutorialExecutionPlanService(TutorialService(StubTutorialRepository(tutorial))).build(
        candidate,
    )

    assert plan.revision_number == tutorial.revision_number
    assert plan.compatibility_status == "verified"
    assert plan.allowed_transition_ids == (open_chat_transition.transition_id,)
