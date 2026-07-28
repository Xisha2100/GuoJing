"""Version-aware decisions about reusing a matched tutorial node."""

from dataclasses import dataclass
from enum import StrEnum

from guojing.domain.tutorials.matching import ScreenMatchResult, ScreenMatchStatus
from guojing.domain.tutorials.models import (
    AppIdentity,
    RiskLevel,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)


class ReuseReason(StrEnum):
    """Why a node received its current compatibility status."""

    SAME_VERIFIED_VERSION = "same_verified_version"
    STORED_STALE = "stored_stale"
    CURRENT_SCREEN_MISMATCH = "current_screen_mismatch"
    CURRENT_SCREEN_UNCERTAIN = "current_screen_uncertain"
    NODE_PROVISIONAL = "node_provisional"
    VERSION_CHANGED_AWAITING_TRANSITION = "version_changed_awaiting_transition"
    LOW_RISK_TRANSITION_CONFIRMED = "low_risk_transition_confirmed"
    EXPECTED_NEXT_STATE_MISMATCH = "expected_next_state_mismatch"
    EXPECTED_NEXT_STATE_UNCERTAIN = "expected_next_state_uncertain"
    HIGH_RISK_REQUIRES_REVIEW = "high_risk_requires_review"
    TERMINAL_NODE_VERSION_CHANGED = "terminal_node_version_changed"


@dataclass(frozen=True, slots=True)
class ReuseAssessment:
    """Compatibility decision; safety-mode authorization is evaluated elsewhere."""

    status: VerificationStatus
    can_attempt_transition: bool
    requires_admin_review: bool
    reason: ReuseReason


_HIGH_RISK_LEVELS = frozenset({RiskLevel.IRREVERSIBLE, RiskLevel.FINANCIAL})


def assess_node_reuse(
    node: TutorialNode,
    current_app: AppIdentity,
    screen_match: ScreenMatchResult,
    transition: TutorialTransition | None = None,
    expected_next_state_match: ScreenMatchStatus | None = None,
) -> ReuseAssessment:
    """Assess reuse without mutating the recorded tutorial.

    A low-risk transition on a new app version may be attempted once and promoted
    only after its expected next state matches. High-risk transitions never
    self-promote and require an administrator review.
    """
    if transition is not None and transition.source_node_id != node.node_id:
        raise ValueError("transition source must match the assessed node")
    if transition is None and expected_next_state_match is not None:
        raise ValueError("next-state evidence requires a transition")

    if node.verification_status is VerificationStatus.STALE:
        return ReuseAssessment(
            VerificationStatus.STALE,
            can_attempt_transition=False,
            requires_admin_review=True,
            reason=ReuseReason.STORED_STALE,
        )

    if screen_match.status is ScreenMatchStatus.MISMATCH:
        return ReuseAssessment(
            VerificationStatus.STALE,
            can_attempt_transition=False,
            requires_admin_review=False,
            reason=ReuseReason.CURRENT_SCREEN_MISMATCH,
        )

    if screen_match.status is ScreenMatchStatus.UNCERTAIN:
        return ReuseAssessment(
            VerificationStatus.PROVISIONAL,
            can_attempt_transition=False,
            requires_admin_review=False,
            reason=ReuseReason.CURRENT_SCREEN_UNCERTAIN,
        )

    if expected_next_state_match is ScreenMatchStatus.MISMATCH:
        return ReuseAssessment(
            VerificationStatus.STALE,
            can_attempt_transition=False,
            requires_admin_review=True,
            reason=ReuseReason.EXPECTED_NEXT_STATE_MISMATCH,
        )

    if expected_next_state_match is ScreenMatchStatus.UNCERTAIN:
        requires_review = transition is not None and transition.risk_level in _HIGH_RISK_LEVELS
        return ReuseAssessment(
            VerificationStatus.PROVISIONAL,
            can_attempt_transition=False,
            requires_admin_review=requires_review,
            reason=ReuseReason.EXPECTED_NEXT_STATE_UNCERTAIN,
        )

    same_verified_version = (
        node.verification_status is VerificationStatus.VERIFIED
        and node.last_verified_version_code == current_app.version_code
    )
    if same_verified_version:
        return ReuseAssessment(
            VerificationStatus.VERIFIED,
            can_attempt_transition=True,
            requires_admin_review=False,
            reason=ReuseReason.SAME_VERIFIED_VERSION,
        )

    if transition is None:
        return ReuseAssessment(
            VerificationStatus.PROVISIONAL,
            can_attempt_transition=False,
            requires_admin_review=False,
            reason=ReuseReason.TERMINAL_NODE_VERSION_CHANGED,
        )

    if transition.risk_level in _HIGH_RISK_LEVELS:
        return ReuseAssessment(
            VerificationStatus.PROVISIONAL,
            can_attempt_transition=False,
            requires_admin_review=True,
            reason=ReuseReason.HIGH_RISK_REQUIRES_REVIEW,
        )

    if expected_next_state_match is ScreenMatchStatus.MATCHED:
        return ReuseAssessment(
            VerificationStatus.VERIFIED,
            can_attempt_transition=True,
            requires_admin_review=False,
            reason=ReuseReason.LOW_RISK_TRANSITION_CONFIRMED,
        )

    return ReuseAssessment(
        VerificationStatus.PROVISIONAL,
        can_attempt_transition=True,
        requires_admin_review=False,
        reason=(
            ReuseReason.NODE_PROVISIONAL
            if node.verification_status is VerificationStatus.PROVISIONAL
            else ReuseReason.VERSION_CHANGED_AWAITING_TRANSITION
        ),
    )
