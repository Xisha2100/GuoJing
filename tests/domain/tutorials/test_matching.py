"""Tests for deterministic tutorial screen matching."""

import pytest

from guojing.domain.tutorials.matching import (
    AnchorEvidence,
    MatchPolicy,
    ScreenMatchReason,
    ScreenMatchStatus,
    ScreenObservation,
    match_screen,
)
from guojing.domain.tutorials.models import AppIdentity, TutorialGraph, TutorialNode


def test_matching_accepts_strong_semantic_and_structural_evidence(
    tutorial_graph: TutorialGraph,
    chat_list_node: TutorialNode,
    recorded_app: AppIdentity,
) -> None:
    observation = ScreenObservation(
        app=recorded_app,
        anchor_evidence=(
            AnchorEvidence("chat_tab", 0.99),
            AnchorEvidence("family_chat", 0.97),
            AnchorEvidence("search", 0.90),
        ),
        structure_score=0.95,
    )

    result = match_screen(tutorial_graph, chat_list_node, observation)

    assert result.status is ScreenMatchStatus.MATCHED
    assert result.score > 0.90
    assert result.reasons == (ScreenMatchReason.STRONG_MATCH,)


def test_matching_treats_missing_required_anchor_as_uncertain(
    tutorial_graph: TutorialGraph,
    chat_list_node: TutorialNode,
    recorded_app: AppIdentity,
) -> None:
    observation = ScreenObservation(
        app=recorded_app,
        anchor_evidence=(AnchorEvidence("chat_tab", 0.99),),
        structure_score=0.92,
    )

    result = match_screen(tutorial_graph, chat_list_node, observation)

    assert result.status is ScreenMatchStatus.UNCERTAIN
    assert result.missing_required == ("family_chat",)
    assert result.reasons == (ScreenMatchReason.REQUIRED_ANCHOR_MISSING,)


def test_matching_rejects_forbidden_anchor_even_when_required_anchors_match(
    tutorial_graph: TutorialGraph,
    chat_list_node: TutorialNode,
    recorded_app: AppIdentity,
) -> None:
    observation = ScreenObservation(
        app=recorded_app,
        anchor_evidence=(
            AnchorEvidence("chat_tab", 0.99),
            AnchorEvidence("family_chat", 0.99),
            AnchorEvidence("payment_password", 0.95),
        ),
        structure_score=0.99,
    )

    result = match_screen(tutorial_graph, chat_list_node, observation)

    assert result.status is ScreenMatchStatus.MISMATCH
    assert result.matched_forbidden == ("payment_password",)
    assert result.reasons == (ScreenMatchReason.FORBIDDEN_ANCHOR_PRESENT,)


def test_matching_rejects_different_android_package(
    tutorial_graph: TutorialGraph,
    chat_list_node: TutorialNode,
) -> None:
    observation = ScreenObservation(
        app=AppIdentity("com.example.fake", "1.0", 1),
        anchor_evidence=(
            AnchorEvidence("chat_tab", 1),
            AnchorEvidence("family_chat", 1),
        ),
        structure_score=1,
    )

    result = match_screen(tutorial_graph, chat_list_node, observation)

    assert result.status is ScreenMatchStatus.MISMATCH
    assert result.reasons == (ScreenMatchReason.PACKAGE_MISMATCH,)


def test_matching_does_not_reject_new_version_by_itself(
    tutorial_graph: TutorialGraph,
    chat_list_node: TutorialNode,
) -> None:
    upgraded_app = AppIdentity("com.tencent.mm", "8.1.0", 2700)
    observation = ScreenObservation(
        app=upgraded_app,
        anchor_evidence=(
            AnchorEvidence("chat_tab", 1),
            AnchorEvidence("family_chat", 1),
            AnchorEvidence("search", 1),
        ),
        structure_score=1,
    )

    result = match_screen(tutorial_graph, chat_list_node, observation)

    assert result.status is ScreenMatchStatus.MATCHED


def test_optional_anchor_can_disappear_without_invalidating_screen(
    tutorial_graph: TutorialGraph,
    chat_list_node: TutorialNode,
    recorded_app: AppIdentity,
) -> None:
    observation = ScreenObservation(
        app=recorded_app,
        anchor_evidence=(
            AnchorEvidence("chat_tab", 1),
            AnchorEvidence("family_chat", 1),
        ),
        structure_score=1,
    )

    result = match_screen(tutorial_graph, chat_list_node, observation)

    assert result.status is ScreenMatchStatus.MATCHED
    assert result.matched_optional == ()


def test_match_evidence_rejects_non_finite_confidence() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        AnchorEvidence("chat_tab", float("nan"))


def test_match_policy_requires_weights_to_add_up_to_one() -> None:
    with pytest.raises(ValueError, match="add up to 1"):
        MatchPolicy(required_weight=0.5)
