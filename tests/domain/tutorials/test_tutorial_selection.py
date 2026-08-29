"""Tests for deterministic tutorial selection from controlled evidence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from guojing.application.tutorials.matcher import (
    TutorialMatchReason,
    TutorialMatchService,
    TutorialMatchStatus,
)
from guojing.application.tutorials.models import (
    PublishedTutorial,
    PublishedTutorialSummary,
    TutorialRevision,
)
from guojing.application.tutorials.service import TutorialService
from guojing.domain.evidence import (
    EvidenceAnchor,
    EvidenceEnvelope,
    EvidenceSharingPolicy,
    EvidenceSource,
)
from guojing.domain.tutorials.models import AppIdentity, TutorialGraph


class StubTutorialRepository:
    def __init__(self, graphs: tuple[TutorialGraph, ...]) -> None:
        self._published = {
            graph.graph_id: PublishedTutorial(
                graph=graph,
                revision_number=1,
                published_at=datetime(2026, 8, 1, tzinfo=UTC),
            )
            for graph in graphs
        }

    def create_revision(self, graph: TutorialGraph) -> TutorialRevision:  # pragma: no cover
        raise NotImplementedError

    def publish_revision(
        self, graph_id: str, revision_number: int
    ) -> PublishedTutorial:  # pragma: no cover
        raise NotImplementedError

    def list_published(self) -> tuple[PublishedTutorialSummary, ...]:
        return tuple(
            PublishedTutorialSummary(
                graph_id=tutorial.graph.graph_id,
                title=tutorial.graph.title,
                package_name=tutorial.graph.recorded_app.package_name,
                recorded_version_name=tutorial.graph.recorded_app.version_name,
                recorded_version_code=tutorial.graph.recorded_app.version_code,
                revision_number=tutorial.revision_number,
                published_at=tutorial.published_at,
            )
            for tutorial in self._published.values()
        )

    def get_published(self, graph_id: str) -> PublishedTutorial:
        return self._published[graph_id]


def _evidence(app: AppIdentity, *, confidence: float = 1.0) -> EvidenceEnvelope:
    captured = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    return EvidenceEnvelope(
        evidence_id=uuid4(),
        request_id=uuid4(),
        package_name=app.package_name,
        version_name=app.version_name,
        version_code=app.version_code,
        source=EvidenceSource.ACCESSIBILITY,
        sharing_policy=EvidenceSharingPolicy.SANITIZED_NETWORK_ALLOWED,
        structure_score=confidence,
        captured_at=captured,
        expires_at=captured + timedelta(minutes=5),
        anchors=(
            EvidenceAnchor("chat_tab", confidence),
            EvidenceAnchor("family_chat", confidence),
            EvidenceAnchor("search", confidence),
        ),
    )


def test_selects_highest_scoring_node(
    tutorial_graph: TutorialGraph,
    recorded_app: AppIdentity,
) -> None:
    service = TutorialMatchService(TutorialService(StubTutorialRepository((tutorial_graph,))))

    decision = service.select(_evidence(recorded_app))

    assert decision.status is TutorialMatchStatus.MATCHED
    assert decision.reason is TutorialMatchReason.STRONG_MATCH
    assert decision.candidate is not None
    assert decision.candidate.graph_id == tutorial_graph.graph_id
    assert decision.candidate.node_id == "chat_list"


def test_unknown_package_returns_no_tutorial(
    tutorial_graph: TutorialGraph,
    recorded_app: AppIdentity,
) -> None:
    service = TutorialMatchService(TutorialService(StubTutorialRepository((tutorial_graph,))))
    unknown_app = replace(recorded_app, package_name="com.example.unknown")

    decision = service.select(_evidence(unknown_app))

    assert decision.status is TutorialMatchStatus.NO_TUTORIAL
    assert decision.reason is TutorialMatchReason.NO_PUBLISHED_TUTORIAL


def test_weak_evidence_stops_without_selecting_a_step(
    tutorial_graph: TutorialGraph,
    recorded_app: AppIdentity,
) -> None:
    service = TutorialMatchService(TutorialService(StubTutorialRepository((tutorial_graph,))))

    decision = service.select(_evidence(recorded_app, confidence=0.5))

    assert decision.status is TutorialMatchStatus.UNCERTAIN
    assert decision.reason is TutorialMatchReason.SCREEN_EVIDENCE_UNCERTAIN


def test_new_app_version_requires_review(
    tutorial_graph: TutorialGraph,
    recorded_app: AppIdentity,
) -> None:
    service = TutorialMatchService(TutorialService(StubTutorialRepository((tutorial_graph,))))
    upgraded_app = replace(recorded_app, version_name="8.1.0", version_code=2_700)

    decision = service.select(_evidence(upgraded_app))

    assert decision.status is TutorialMatchStatus.UNCERTAIN
    assert decision.reason is TutorialMatchReason.VERSION_REQUIRES_REVIEW
