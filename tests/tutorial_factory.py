"""Small valid tutorial graphs shared by application and adapter tests."""

from dataclasses import replace

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


def make_tutorial_graph(
    *,
    graph_id: str = "wechat_open_family_chat",
    package_name: str = "com.tencent.mm",
    title: str = "打开家人微信聊天",
) -> TutorialGraph:
    start = TutorialNode(
        node_id="chat_list",
        title="微信聊天列表",
        anchors=(
            ScreenAnchor(
                anchor_id="family_chat",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(text="家人"),
            ),
        ),
        privacy_mode=PrivacyMode.LOCAL_ONLY,
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=2600,
    )
    end = TutorialNode(
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
        last_verified_version_code=2600,
    )
    return TutorialGraph(
        graph_id=graph_id,
        title=title,
        recorded_app=AppIdentity(
            package_name=package_name,
            version_name="8.0.60",
            version_code=2600,
        ),
        start_node_id=start.node_id,
        nodes=(start, end),
        transitions=(
            TutorialTransition(
                transition_id="open_family_chat",
                source_node_id=start.node_id,
                target_node_id=end.node_id,
                action_kind=ActionKind.TAP,
                instruction="点击“家人”聊天",
                risk_level=RiskLevel.LOW,
                target_anchor_id="family_chat",
            ),
        ),
    )


def with_title(graph: TutorialGraph, title: str) -> TutorialGraph:
    return replace(graph, title=title)
