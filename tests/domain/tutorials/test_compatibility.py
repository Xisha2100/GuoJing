"""Tests for version-aware tutorial node reuse decisions."""

from dataclasses import replace

from guojing.domain.tutorials.compatibility import ReuseReason, assess_node_reuse
from guojing.domain.tutorials.matching import (
    ScreenMatchReason,
    ScreenMatchResult,
    ScreenMatchStatus,
)
from guojing.domain.tutorials.models import (
    AppIdentity,
    RiskLevel,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)


def _screen_match(status: ScreenMatchStatus = ScreenMatchStatus.MATCHED) -> ScreenMatchResult:
    reason = (
        ScreenMatchReason.STRONG_MATCH
        if status is ScreenMatchStatus.MATCHED
        else ScreenMatchReason.REQUIRED_ANCHOR_MISSING
    )
    return ScreenMatchResult(
        status=status,
        score=0.98 if status is ScreenMatchStatus.MATCHED else 0.60,
        matched_required=("chat_tab",),
        missing_required=() if status is ScreenMatchStatus.MATCHED else ("family_chat",),
        matched_optional=(),
        matched_forbidden=(),
        reasons=(reason,),
    )


def test_same_verified_version_is_immediately_reusable(
    chat_list_node: TutorialNode,
    recorded_app: AppIdentity,
    open_chat_transition: TutorialTransition,
) -> None:
    assessment = assess_node_reuse(
        chat_list_node,
        recorded_app,
        _screen_match(),
        open_chat_transition,
    )

    assert assessment.status is VerificationStatus.VERIFIED
    assert assessment.can_attempt_transition is True
    assert assessment.requires_admin_review is False
    assert assessment.reason is ReuseReason.SAME_VERIFIED_VERSION


def test_new_version_can_trial_low_risk_transition(
    chat_list_node: TutorialNode,
    open_chat_transition: TutorialTransition,
) -> None:
    upgraded_app = AppIdentity("com.tencent.mm", "8.1.0", 2700)

    assessment = assess_node_reuse(
        chat_list_node,
        upgraded_app,
        _screen_match(),
        open_chat_transition,
    )

    assert assessment.status is VerificationStatus.PROVISIONAL
    assert assessment.can_attempt_transition is True
    assert assessment.reason is ReuseReason.VERSION_CHANGED_AWAITING_TRANSITION


def test_low_risk_transition_promotes_after_expected_state_matches(
    chat_list_node: TutorialNode,
    open_chat_transition: TutorialTransition,
) -> None:
    upgraded_app = AppIdentity("com.tencent.mm", "8.1.0", 2700)

    assessment = assess_node_reuse(
        chat_list_node,
        upgraded_app,
        _screen_match(),
        open_chat_transition,
        expected_next_state_match=ScreenMatchStatus.MATCHED,
    )

    assert assessment.status is VerificationStatus.VERIFIED
    assert assessment.reason is ReuseReason.LOW_RISK_TRANSITION_CONFIRMED


def test_high_risk_transition_never_self_promotes_on_new_version(
    chat_list_node: TutorialNode,
    open_chat_transition: TutorialTransition,
) -> None:
    upgraded_app = AppIdentity("com.tencent.mm", "8.1.0", 2700)
    financial_transition = replace(open_chat_transition, risk_level=RiskLevel.FINANCIAL)

    assessment = assess_node_reuse(
        chat_list_node,
        upgraded_app,
        _screen_match(),
        financial_transition,
        expected_next_state_match=ScreenMatchStatus.MATCHED,
    )

    assert assessment.status is VerificationStatus.PROVISIONAL
    assert assessment.can_attempt_transition is False
    assert assessment.requires_admin_review is True
    assert assessment.reason is ReuseReason.HIGH_RISK_REQUIRES_REVIEW


def test_failed_expected_transition_marks_observation_stale(
    chat_list_node: TutorialNode,
    open_chat_transition: TutorialTransition,
) -> None:
    upgraded_app = AppIdentity("com.tencent.mm", "8.1.0", 2700)

    assessment = assess_node_reuse(
        chat_list_node,
        upgraded_app,
        _screen_match(),
        open_chat_transition,
        expected_next_state_match=ScreenMatchStatus.MISMATCH,
    )

    assert assessment.status is VerificationStatus.STALE
    assert assessment.can_attempt_transition is False
    assert assessment.reason is ReuseReason.EXPECTED_NEXT_STATE_MISMATCH


def test_uncertain_expected_state_stops_repeating_the_action(
    chat_list_node: TutorialNode,
    open_chat_transition: TutorialTransition,
) -> None:
    upgraded_app = AppIdentity("com.tencent.mm", "8.1.0", 2700)

    assessment = assess_node_reuse(
        chat_list_node,
        upgraded_app,
        _screen_match(),
        open_chat_transition,
        expected_next_state_match=ScreenMatchStatus.UNCERTAIN,
    )

    assert assessment.status is VerificationStatus.PROVISIONAL
    assert assessment.can_attempt_transition is False
    assert assessment.reason is ReuseReason.EXPECTED_NEXT_STATE_UNCERTAIN


def test_uncertain_screen_never_attempts_transition(
    chat_list_node: TutorialNode,
    recorded_app: AppIdentity,
    open_chat_transition: TutorialTransition,
) -> None:
    assessment = assess_node_reuse(
        chat_list_node,
        recorded_app,
        _screen_match(ScreenMatchStatus.UNCERTAIN),
        open_chat_transition,
    )

    assert assessment.status is VerificationStatus.PROVISIONAL
    assert assessment.can_attempt_transition is False
    assert assessment.reason is ReuseReason.CURRENT_SCREEN_UNCERTAIN


def test_stored_stale_node_always_requires_review(
    chat_list_node: TutorialNode,
    recorded_app: AppIdentity,
    open_chat_transition: TutorialTransition,
) -> None:
    stale_node = replace(chat_list_node, verification_status=VerificationStatus.STALE)

    assessment = assess_node_reuse(
        stale_node,
        recorded_app,
        _screen_match(),
        open_chat_transition,
    )

    assert assessment.status is VerificationStatus.STALE
    assert assessment.requires_admin_review is True
    assert assessment.reason is ReuseReason.STORED_STALE
