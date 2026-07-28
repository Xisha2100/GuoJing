"""Tests for tutorial graph structural validation."""

from dataclasses import replace

import pytest

from guojing.domain.tutorials.models import (
    ActionKind,
    AnchorRole,
    PrivacyMode,
    RiskLevel,
    ScreenAnchor,
    SemanticLocator,
    TutorialGraph,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)
from guojing.domain.tutorials.validation import (
    GraphIssueCode,
    InvalidTutorialGraph,
    require_valid_tutorial_graph,
    validate_tutorial_graph,
)


def test_valid_graph_has_no_structural_issues(tutorial_graph: TutorialGraph) -> None:
    assert validate_tutorial_graph(tutorial_graph) == ()


def test_validation_reports_duplicate_and_unreachable_nodes(
    tutorial_graph: TutorialGraph,
) -> None:
    detached_node = TutorialNode(
        node_id="detached",
        title="未连接页面",
        anchors=(
            ScreenAnchor(
                anchor_id="title",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(text="未连接"),
            ),
        ),
        privacy_mode=PrivacyMode.NETWORK_ALLOWED,
        verification_status=VerificationStatus.PROVISIONAL,
    )
    invalid_graph = replace(
        tutorial_graph,
        nodes=(*tutorial_graph.nodes, tutorial_graph.nodes[0], detached_node),
    )

    codes = {issue.code for issue in validate_tutorial_graph(invalid_graph)}

    assert GraphIssueCode.DUPLICATE_NODE_ID in codes
    assert GraphIssueCode.UNREACHABLE_NODE in codes


def test_validation_rejects_action_without_required_target(
    tutorial_graph: TutorialGraph,
) -> None:
    invalid_transition = replace(
        tutorial_graph.transitions[0],
        action_kind=ActionKind.HOLD,
        target_anchor_id=None,
    )
    invalid_graph = replace(tutorial_graph, transitions=(invalid_transition,))

    issues = validate_tutorial_graph(invalid_graph)

    assert [issue.code for issue in issues] == [GraphIssueCode.MISSING_TARGET_ANCHOR]


def test_validation_rejects_targeting_forbidden_anchor(
    tutorial_graph: TutorialGraph,
) -> None:
    invalid_transition = replace(
        tutorial_graph.transitions[0],
        target_anchor_id="payment_password",
        risk_level=RiskLevel.FINANCIAL,
    )
    invalid_graph = replace(tutorial_graph, transitions=(invalid_transition,))

    issues = validate_tutorial_graph(invalid_graph)

    assert [issue.code for issue in issues] == [GraphIssueCode.FORBIDDEN_TARGET_ANCHOR]


def test_require_valid_graph_raises_with_all_issues(tutorial_graph: TutorialGraph) -> None:
    node_without_required_anchor = replace(
        tutorial_graph.nodes[0],
        anchors=(
            ScreenAnchor(
                anchor_id="optional_title",
                role=AnchorRole.OPTIONAL,
                locator=SemanticLocator(text="标题"),
            ),
        ),
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=None,
    )
    invalid_graph = replace(
        tutorial_graph,
        nodes=(node_without_required_anchor, tutorial_graph.nodes[1]),
    )

    with pytest.raises(InvalidTutorialGraph) as error:
        require_valid_tutorial_graph(invalid_graph)

    codes = {issue.code for issue in error.value.issues}
    assert codes == {
        GraphIssueCode.NO_REQUIRED_ANCHOR,
        GraphIssueCode.VERIFIED_WITHOUT_VERSION,
        GraphIssueCode.UNKNOWN_TARGET_ANCHOR,
    }


def test_validation_rejects_graph_without_terminal_node(
    tutorial_graph: TutorialGraph,
) -> None:
    return_transition = TutorialTransition(
        transition_id="return_to_chat_list",
        source_node_id="conversation",
        target_node_id="chat_list",
        action_kind=ActionKind.SYSTEM_BACK,
        instruction="返回聊天列表",
        risk_level=RiskLevel.LOW,
    )
    cyclic_graph = replace(
        tutorial_graph,
        transitions=(*tutorial_graph.transitions, return_transition),
    )

    codes = {issue.code for issue in validate_tutorial_graph(cyclic_graph)}

    assert GraphIssueCode.NO_TERMINAL_NODE in codes
