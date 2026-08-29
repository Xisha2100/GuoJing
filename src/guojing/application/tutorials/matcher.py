"""Deterministic selection of a published tutorial from an evidence envelope."""

from dataclasses import dataclass
from enum import StrEnum

from guojing.application.tutorials.models import PublishedTutorial
from guojing.application.tutorials.service import TutorialService
from guojing.domain.evidence import EvidenceEnvelope
from guojing.domain.tutorials.compatibility import ReuseAssessment, assess_node_reuse
from guojing.domain.tutorials.matching import (
    AnchorEvidence,
    ScreenMatchResult,
    ScreenMatchStatus,
    ScreenObservation,
    match_screen,
)
from guojing.domain.tutorials.models import AppIdentity, TutorialNode


class TutorialMatchStatus(StrEnum):
    """Selection status consumed by the processing graph."""

    MATCHED = "matched"
    UNCERTAIN = "uncertain"
    NO_TUTORIAL = "no_tutorial"


class TutorialMatchReason(StrEnum):
    """Machine-readable reason for a selection result."""

    STRONG_MATCH = "strong_match"
    NO_PUBLISHED_TUTORIAL = "no_published_tutorial"
    NO_SCREEN_MATCH = "no_screen_match"
    SCREEN_EVIDENCE_UNCERTAIN = "screen_evidence_uncertain"
    VERSION_REQUIRES_REVIEW = "version_requires_review"
    STORED_NODE_REQUIRES_REVIEW = "stored_node_requires_review"


@dataclass(frozen=True, slots=True)
class TutorialMatchCandidate:
    """One graph/node comparison retained for diagnostics."""

    graph_id: str
    node_id: str
    revision_number: int
    screen_match: ScreenMatchResult
    reuse_assessment: ReuseAssessment


@dataclass(frozen=True, slots=True)
class TutorialMatchDecision:
    """The best deterministic candidate, or an explicit stop condition."""

    status: TutorialMatchStatus
    reason: TutorialMatchReason
    candidate: TutorialMatchCandidate | None
    considered_candidates: tuple[TutorialMatchCandidate, ...]


class TutorialMatchService:
    """Choose a current tutorial without fuzzy model guesses or side effects."""

    def __init__(self, tutorial_service: TutorialService) -> None:
        self._tutorial_service = tutorial_service

    def select(self, envelope: EvidenceEnvelope) -> TutorialMatchDecision:
        """Match all nodes for the exact package and fail closed on uncertainty."""
        tutorials = self._tutorial_service.list_published_for_package(envelope.package_name)
        if not tutorials:
            return TutorialMatchDecision(
                TutorialMatchStatus.NO_TUTORIAL,
                TutorialMatchReason.NO_PUBLISHED_TUTORIAL,
                None,
                (),
            )

        observation = _to_observation(envelope)
        candidates = tuple(
            _candidate(tutorial, node, observation)
            for tutorial in tutorials
            for node in tutorial.graph.nodes
        )
        screen_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.screen_match.status is not ScreenMatchStatus.MISMATCH
        )
        if not screen_candidates:
            return TutorialMatchDecision(
                TutorialMatchStatus.NO_TUTORIAL,
                TutorialMatchReason.NO_SCREEN_MATCH,
                None,
                candidates,
            )

        best = max(
            screen_candidates,
            key=lambda candidate: (
                candidate.screen_match.score,
                candidate.screen_match.status is ScreenMatchStatus.MATCHED,
                candidate.graph_id,
                candidate.node_id,
            ),
        )
        if best.screen_match.status is not ScreenMatchStatus.MATCHED:
            reason = TutorialMatchReason.SCREEN_EVIDENCE_UNCERTAIN
            status = TutorialMatchStatus.UNCERTAIN
        elif best.reuse_assessment.requires_admin_review:
            reason = TutorialMatchReason.STORED_NODE_REQUIRES_REVIEW
            status = TutorialMatchStatus.UNCERTAIN
        elif not best.reuse_assessment.can_attempt_transition:
            reason = TutorialMatchReason.VERSION_REQUIRES_REVIEW
            status = TutorialMatchStatus.UNCERTAIN
        else:
            reason = TutorialMatchReason.STRONG_MATCH
            status = TutorialMatchStatus.MATCHED
        return TutorialMatchDecision(status, reason, best, candidates)


def _to_observation(envelope: EvidenceEnvelope) -> ScreenObservation:
    return ScreenObservation(
        app=AppIdentity(
            package_name=envelope.package_name,
            version_name=envelope.version_name,
            version_code=envelope.version_code,
        ),
        anchor_evidence=tuple(
            AnchorEvidence(anchor.anchor_id, anchor.confidence) for anchor in envelope.anchors
        ),
        structure_score=envelope.structure_score,
    )


def _candidate(
    tutorial: PublishedTutorial,
    node: TutorialNode,
    observation: ScreenObservation,
) -> TutorialMatchCandidate:
    screen_match = match_screen(tutorial.graph, node, observation)
    reuse_assessment = assess_node_reuse(
        node,
        observation.app,
        screen_match,
    )
    return TutorialMatchCandidate(
        graph_id=tutorial.graph.graph_id,
        node_id=node.node_id,
        revision_number=tutorial.revision_number,
        screen_match=screen_match,
        reuse_assessment=reuse_assessment,
    )
