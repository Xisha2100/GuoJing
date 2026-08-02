"""Safety and completeness rules for incremental tutorial authoring."""

from dataclasses import replace

import pytest

from guojing.domain.tutorials.authoring import (
    AnchorCandidate,
    CandidateSource,
    CaptureArtifactKind,
    CaptureArtifactReference,
    CaptureSharingPolicy,
    DraftIssueCode,
    DraftTutorialGraph,
    IncompleteTutorialDraft,
    ReviewDecision,
    ScreenCapture,
    TutorialDraftDocument,
    build_tutorial_graph,
)
from tests.tutorial_factory import make_tutorial_graph


def _artifact() -> CaptureArtifactReference:
    return CaptureArtifactReference(
        artifact_id="asset-1",
        kind=CaptureArtifactKind.SCREENSHOT,
        sha256="a" * 64,
    )


def test_local_only_capture_cannot_send_artifacts_or_candidates() -> None:
    with pytest.raises(ValueError, match="local-only"):
        ScreenCapture(
            capture_id="capture-1",
            sharing_policy=CaptureSharingPolicy.LOCAL_ONLY,
            artifacts=(_artifact(),),
        )


def test_generated_candidate_needs_admin_review_before_decision() -> None:
    anchor = make_tutorial_graph().nodes[0].anchors[0]

    with pytest.raises(ValueError, match="admin reviewer"):
        AnchorCandidate(
            candidate_id="candidate-1",
            source=CandidateSource.AI,
            suggested_anchor=anchor,
            decision=ReviewDecision.ACCEPTED,
        )

    accepted = AnchorCandidate(
        candidate_id="candidate-1",
        source=CandidateSource.AI,
        suggested_anchor=anchor,
        decision=ReviewDecision.ACCEPTED,
        reviewed_by="bootstrap-admin",
    )

    assert accepted.decision is ReviewDecision.ACCEPTED


def test_incomplete_document_reports_every_missing_top_level_field() -> None:
    with pytest.raises(IncompleteTutorialDraft) as captured:
        build_tutorial_graph(TutorialDraftDocument())

    assert {issue.code for issue in captured.value.issues} == {
        DraftIssueCode.MISSING_GRAPH_ID,
        DraftIssueCode.MISSING_TITLE,
        DraftIssueCode.MISSING_RECORDED_APP,
        DraftIssueCode.MISSING_START_NODE,
        DraftIssueCode.NO_NODES,
    }


def test_complete_document_builds_the_existing_tutorial_graph() -> None:
    graph = make_tutorial_graph()
    document = TutorialDraftDocument(
        graph=DraftTutorialGraph(
            graph_id=graph.graph_id,
            title=graph.title,
            recorded_app=graph.recorded_app,
            start_node_id=graph.start_node_id,
            nodes=graph.nodes,
            transitions=graph.transitions,
        ),
        captures=(
            ScreenCapture(
                capture_id="capture-1",
                sharing_policy=CaptureSharingPolicy.SANITIZED,
                artifacts=(_artifact(),),
            ),
        ),
    )

    assert build_tutorial_graph(document) == graph


def test_proposed_candidate_cannot_claim_a_reviewer() -> None:
    anchor = make_tutorial_graph().nodes[0].anchors[0]
    candidate = AnchorCandidate(
        candidate_id="candidate-1",
        source=CandidateSource.OCR,
        suggested_anchor=anchor,
    )

    with pytest.raises(ValueError, match="must not have a reviewer"):
        replace(candidate, reviewed_by="bootstrap-admin")


def test_editor_document_rejects_duplicate_capture_ids() -> None:
    capture = ScreenCapture(
        capture_id="capture-1",
        sharing_policy=CaptureSharingPolicy.SANITIZED,
    )

    with pytest.raises(ValueError, match="capture_id values must be unique"):
        TutorialDraftDocument(captures=(capture, capture))


def test_screen_capture_rejects_duplicate_candidate_ids() -> None:
    candidate = AnchorCandidate(
        candidate_id="candidate-1",
        source=CandidateSource.ACCESSIBILITY,
        suggested_anchor=make_tutorial_graph().nodes[0].anchors[0],
    )

    with pytest.raises(ValueError, match="candidate_id values must be unique"):
        ScreenCapture(
            capture_id="capture-1",
            sharing_policy=CaptureSharingPolicy.SANITIZED,
            candidates=(candidate, candidate),
        )
