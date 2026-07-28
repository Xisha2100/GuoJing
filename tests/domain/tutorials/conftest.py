"""Reusable tutorial graph fixtures."""

import pytest

from guojing.domain.tutorials.models import (
    ActionKind,
    AnchorRole,
    AppIdentity,
    NormalizedBounds,
    PrivacyMode,
    RelativeConstraint,
    RelativePosition,
    RiskLevel,
    ScreenAnchor,
    SemanticLocator,
    TutorialGraph,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)


@pytest.fixture
def recorded_app() -> AppIdentity:
    return AppIdentity(
        package_name="com.tencent.mm",
        version_name="8.0.60",
        version_code=2600,
    )


@pytest.fixture
def chat_list_node() -> TutorialNode:
    return TutorialNode(
        node_id="chat_list",
        title="微信聊天列表",
        anchors=(
            ScreenAnchor(
                anchor_id="chat_tab",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(resource_id="com.tencent.mm:id/chat_tab"),
            ),
            ScreenAnchor(
                anchor_id="family_chat",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(text="家人"),
                relative_constraints=(
                    RelativeConstraint(
                        reference_anchor_id="chat_tab",
                        position=RelativePosition.ABOVE,
                    ),
                ),
                bounds_fallback=NormalizedBounds(0.02, 0.15, 0.98, 0.28),
            ),
            ScreenAnchor(
                anchor_id="search",
                role=AnchorRole.OPTIONAL,
                locator=SemanticLocator(content_description="搜索"),
            ),
            ScreenAnchor(
                anchor_id="payment_password",
                role=AnchorRole.FORBIDDEN,
                locator=SemanticLocator(ocr_text="支付密码"),
            ),
        ),
        privacy_mode=PrivacyMode.LOCAL_ONLY,
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=2600,
    )


@pytest.fixture
def conversation_node() -> TutorialNode:
    return TutorialNode(
        node_id="conversation",
        title="家人聊天页",
        anchors=(
            ScreenAnchor(
                anchor_id="chat_title",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(text="家人"),
            ),
            ScreenAnchor(
                anchor_id="voice_button",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(content_description="切换到按住说话"),
            ),
        ),
        privacy_mode=PrivacyMode.LOCAL_ONLY,
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=2600,
    )


@pytest.fixture
def open_chat_transition() -> TutorialTransition:
    return TutorialTransition(
        transition_id="open_family_chat",
        source_node_id="chat_list",
        target_node_id="conversation",
        action_kind=ActionKind.TAP,
        instruction="点击“家人”聊天",
        risk_level=RiskLevel.LOW,
        target_anchor_id="family_chat",
    )


@pytest.fixture
def tutorial_graph(
    recorded_app: AppIdentity,
    chat_list_node: TutorialNode,
    conversation_node: TutorialNode,
    open_chat_transition: TutorialTransition,
) -> TutorialGraph:
    return TutorialGraph(
        graph_id="wechat_open_family_chat",
        title="打开家人微信聊天",
        recorded_app=recorded_app,
        start_node_id=chat_list_node.node_id,
        nodes=(chat_list_node, conversation_node),
        transitions=(open_chat_transition,),
    )
