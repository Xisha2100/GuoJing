"""Deterministic screen matching based on recorded semantic evidence."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from guojing.domain.tutorials.models import (
    AnchorRole,
    AppIdentity,
    NormalizedBounds,
    RelativePosition,
    ScreenAnchor,
    TutorialGraph,
    TutorialNode,
)


@dataclass(frozen=True, slots=True)
class AnchorEvidence:
    """Confidence that one recorded anchor is present on the current screen."""

    anchor_id: str
    confidence: float
    normalized_bounds: NormalizedBounds | None = None

    def __post_init__(self) -> None:
        if not self.anchor_id.strip():
            raise ValueError("anchor_id must not be blank")
        if not isfinite(self.confidence) or self.confidence < 0 or self.confidence > 1:
            raise ValueError("anchor confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ScreenObservation:
    """Evidence produced on Android without exposing raw screen content."""

    app: AppIdentity
    anchor_evidence: tuple[AnchorEvidence, ...]
    structure_score: float

    def __post_init__(self) -> None:
        if (
            not isfinite(self.structure_score)
            or self.structure_score < 0
            or self.structure_score > 1
        ):
            raise ValueError("structure_score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class MatchPolicy:
    """Tunable thresholds kept outside matching code."""

    anchor_presence_threshold: float = 0.80
    matched_score_threshold: float = 0.90
    required_weight: float = 0.75
    optional_weight: float = 0.10
    structure_weight: float = 0.15

    def __post_init__(self) -> None:
        values = (
            self.anchor_presence_threshold,
            self.matched_score_threshold,
            self.required_weight,
            self.optional_weight,
            self.structure_weight,
        )
        if any(not isfinite(value) or value < 0 or value > 1 for value in values):
            raise ValueError("match policy values must be between 0 and 1")
        weight_sum = self.required_weight + self.optional_weight + self.structure_weight
        if abs(weight_sum - 1) > 1e-9:
            raise ValueError("match policy weights must add up to 1")


class ScreenMatchStatus(StrEnum):
    """Outcome of comparing one observation with one tutorial node."""

    MATCHED = "matched"
    UNCERTAIN = "uncertain"
    MISMATCH = "mismatch"


class ScreenMatchReason(StrEnum):
    """Machine-readable explanation for a screen match outcome."""

    STRONG_MATCH = "strong_match"
    PACKAGE_MISMATCH = "package_mismatch"
    FORBIDDEN_ANCHOR_PRESENT = "forbidden_anchor_present"
    REQUIRED_ANCHOR_MISSING = "required_anchor_missing"
    SCORE_BELOW_THRESHOLD = "score_below_threshold"
    RELATIVE_CONSTRAINT_FAILED = "relative_constraint_failed"


@dataclass(frozen=True, slots=True)
class ScreenMatchResult:
    """Detailed match result suitable for logs and admin diagnostics."""

    status: ScreenMatchStatus
    score: float
    matched_required: tuple[str, ...]
    missing_required: tuple[str, ...]
    matched_optional: tuple[str, ...]
    matched_forbidden: tuple[str, ...]
    reasons: tuple[ScreenMatchReason, ...]


DEFAULT_MATCH_POLICY = MatchPolicy()


def match_screen(
    graph: TutorialGraph,
    node: TutorialNode,
    observation: ScreenObservation,
    policy: MatchPolicy = DEFAULT_MATCH_POLICY,
) -> ScreenMatchResult:
    """Compare local anchor evidence with one recorded node.

    App version intentionally does not participate in the score. It is evaluated
    separately when deciding whether a matched node may be reused after an update.
    """
    if observation.app.package_name != graph.recorded_app.package_name:
        return ScreenMatchResult(
            status=ScreenMatchStatus.MISMATCH,
            score=0,
            matched_required=(),
            missing_required=(),
            matched_optional=(),
            matched_forbidden=(),
            reasons=(ScreenMatchReason.PACKAGE_MISMATCH,),
        )

    confidence_by_anchor: dict[str, float] = {}
    bounds_by_anchor: dict[str, NormalizedBounds] = {}
    for evidence in observation.anchor_evidence:
        previous = confidence_by_anchor.get(evidence.anchor_id, 0)
        confidence_by_anchor[evidence.anchor_id] = max(previous, evidence.confidence)
        if evidence.normalized_bounds is not None:
            bounds_by_anchor[evidence.anchor_id] = evidence.normalized_bounds

    required = tuple(anchor for anchor in node.anchors if anchor.role is AnchorRole.REQUIRED)
    optional = tuple(anchor for anchor in node.anchors if anchor.role is AnchorRole.OPTIONAL)
    forbidden = tuple(anchor for anchor in node.anchors if anchor.role is AnchorRole.FORBIDDEN)

    matched_required, failed_required = _present_anchor_ids(
        required,
        confidence_by_anchor,
        bounds_by_anchor,
        policy,
    )
    missing_required = tuple(
        anchor.anchor_id for anchor in required if anchor.anchor_id not in matched_required
    )
    matched_optional, failed_optional = _present_anchor_ids(
        optional,
        confidence_by_anchor,
        bounds_by_anchor,
        policy,
    )
    matched_forbidden, _ = _present_anchor_ids(
        forbidden,
        confidence_by_anchor,
        bounds_by_anchor,
        policy,
    )

    if matched_forbidden:
        return ScreenMatchResult(
            status=ScreenMatchStatus.MISMATCH,
            score=0,
            matched_required=matched_required,
            missing_required=missing_required,
            matched_optional=matched_optional,
            matched_forbidden=matched_forbidden,
            reasons=(ScreenMatchReason.FORBIDDEN_ANCHOR_PRESENT,),
        )

    required_score = _average_confidence(required, confidence_by_anchor)
    optional_score = _average_confidence(optional, confidence_by_anchor)
    score = (
        policy.required_weight * required_score
        + policy.optional_weight * optional_score
        + policy.structure_weight * observation.structure_score
    )

    if missing_required:
        return ScreenMatchResult(
            status=ScreenMatchStatus.UNCERTAIN,
            score=score,
            matched_required=matched_required,
            missing_required=missing_required,
            matched_optional=matched_optional,
            matched_forbidden=(),
            reasons=(
                (
                    ScreenMatchReason.RELATIVE_CONSTRAINT_FAILED
                    if failed_required
                    else ScreenMatchReason.REQUIRED_ANCHOR_MISSING
                ),
            ),
        )

    if failed_required or failed_optional:
        return ScreenMatchResult(
            status=ScreenMatchStatus.UNCERTAIN,
            score=score,
            matched_required=matched_required,
            missing_required=(),
            matched_optional=matched_optional,
            matched_forbidden=(),
            reasons=(ScreenMatchReason.RELATIVE_CONSTRAINT_FAILED,),
        )

    if score < policy.matched_score_threshold:
        return ScreenMatchResult(
            status=ScreenMatchStatus.UNCERTAIN,
            score=score,
            matched_required=matched_required,
            missing_required=(),
            matched_optional=matched_optional,
            matched_forbidden=(),
            reasons=(ScreenMatchReason.SCORE_BELOW_THRESHOLD,),
        )

    return ScreenMatchResult(
        status=ScreenMatchStatus.MATCHED,
        score=score,
        matched_required=matched_required,
        missing_required=(),
        matched_optional=matched_optional,
        matched_forbidden=(),
        reasons=(ScreenMatchReason.STRONG_MATCH,),
    )


def _present_anchor_ids(
    anchors: tuple[ScreenAnchor, ...],
    confidence_by_anchor: dict[str, float],
    bounds_by_anchor: dict[str, NormalizedBounds],
    policy: MatchPolicy,
) -> tuple[tuple[str, ...], bool]:
    present: list[str] = []
    failed_constraints = False
    for anchor in anchors:
        if confidence_by_anchor.get(anchor.anchor_id, 0) >= policy.anchor_presence_threshold:
            if _relative_constraints_satisfied(anchor, bounds_by_anchor):
                present.append(anchor.anchor_id)
            elif anchor.relative_constraints:
                failed_constraints = True
    return tuple(present), failed_constraints


def _relative_constraints_satisfied(
    anchor: ScreenAnchor,
    bounds_by_anchor: dict[str, NormalizedBounds],
) -> bool:
    if not anchor.relative_constraints:
        return True
    bounds = bounds_by_anchor.get(anchor.anchor_id)
    if bounds is None:
        # Older accessibility producers may provide confidence without bounds;
        # preserve their semantic signal and enforce geometry whenever it is
        # actually available from both anchors.
        return True
    for constraint in anchor.relative_constraints:
        reference = bounds_by_anchor.get(constraint.reference_anchor_id)
        if reference is None:
            continue
        if not _satisfies_position(bounds, reference, constraint.position):
            return False
    return True


def _satisfies_position(
    bounds: NormalizedBounds,
    reference: NormalizedBounds,
    position: RelativePosition,
) -> bool:
    tolerance = 0.02
    if position is RelativePosition.LEFT_OF:
        return bounds.right <= reference.left + tolerance
    if position is RelativePosition.RIGHT_OF:
        return bounds.left + tolerance >= reference.right
    if position is RelativePosition.ABOVE:
        return bounds.bottom <= reference.top + tolerance
    if position is RelativePosition.BELOW:
        return bounds.top + tolerance >= reference.bottom
    if position is RelativePosition.INSIDE:
        return (
            bounds.left >= reference.left - tolerance
            and bounds.right <= reference.right + tolerance
            and bounds.top >= reference.top - tolerance
            and bounds.bottom <= reference.bottom + tolerance
        )
    center_x = (bounds.left + bounds.right) / 2
    center_y = (bounds.top + bounds.bottom) / 2
    reference_x = (reference.left + reference.right) / 2
    reference_y = (reference.top + reference.bottom) / 2
    return abs(center_x - reference_x) <= 0.25 and abs(center_y - reference_y) <= 0.25


def _average_confidence(
    anchors: tuple[ScreenAnchor, ...],
    confidence_by_anchor: dict[str, float],
) -> float:
    if not anchors:
        return 0
    total = 0.0
    for anchor in anchors:
        total += confidence_by_anchor.get(anchor.anchor_id, 0)
    return total / len(anchors)
