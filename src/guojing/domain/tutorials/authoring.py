"""Domain values and safety rules for incremental tutorial authoring."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from re import fullmatch

from guojing.domain.tutorials.models import (
    AppIdentity,
    ScreenAnchor,
    TutorialGraph,
    TutorialNode,
    TutorialTransition,
)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")


class CaptureSharingPolicy(StrEnum):
    """Whether curated recording evidence may be stored by the backend."""

    SANITIZED = "sanitized"
    LOCAL_ONLY = "local_only"


class CaptureArtifactKind(StrEnum):
    """Large capture artifacts stored outside the workspace JSON."""

    SCREENSHOT = "screenshot"
    ACCESSIBILITY_TREE = "accessibility_tree"
    OCR_RESULT = "ocr_result"


class CandidateSource(StrEnum):
    """Producer of a possible screen anchor."""

    ACCESSIBILITY = "accessibility"
    OCR = "ocr"
    MANUAL = "manual"
    AI = "ai"


class ReviewDecision(StrEnum):
    """An administrator's decision about a generated candidate."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CaptureArtifactReference:
    """Opaque reference to one sanitized artifact plus an integrity digest."""

    artifact_id: str
    kind: CaptureArtifactKind
    sha256: str

    def __post_init__(self) -> None:
        _require_non_blank(self.artifact_id, "artifact_id")
        if fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("sha256 must contain 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class AnchorCandidate:
    """A suggested anchor that cannot accept itself without human review."""

    candidate_id: str
    source: CandidateSource
    suggested_anchor: ScreenAnchor
    decision: ReviewDecision = ReviewDecision.PROPOSED
    reviewed_by: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.candidate_id, "candidate_id")
        if self.decision is ReviewDecision.PROPOSED and self.reviewed_by is not None:
            raise ValueError("a proposed candidate must not have a reviewer")
        if self.decision is not ReviewDecision.PROPOSED:
            if self.reviewed_by is None:
                raise ValueError("an accepted or rejected candidate needs an admin reviewer")
            _require_non_blank(self.reviewed_by, "reviewed_by")


@dataclass(frozen=True, slots=True)
class ScreenCapture:
    """Curated evidence used to construct one tutorial screen state."""

    capture_id: str
    sharing_policy: CaptureSharingPolicy
    artifacts: tuple[CaptureArtifactReference, ...] = ()
    candidates: tuple[AnchorCandidate, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank(self.capture_id, "capture_id")
        _require_unique(
            tuple(artifact.artifact_id for artifact in self.artifacts),
            "artifact_id",
        )
        _require_unique(
            tuple(candidate.candidate_id for candidate in self.candidates),
            "candidate_id",
        )
        if self.sharing_policy is CaptureSharingPolicy.LOCAL_ONLY and (
            self.artifacts or self.candidates
        ):
            raise ValueError(
                "local-only captures must not send artifacts or candidate content to the backend"
            )


@dataclass(frozen=True, slots=True)
class DraftTutorialGraph:
    """A graph under construction; complete nodes may be added incrementally."""

    graph_id: str | None = None
    title: str | None = None
    recorded_app: AppIdentity | None = None
    start_node_id: str | None = None
    nodes: tuple[TutorialNode, ...] = ()
    transitions: tuple[TutorialTransition, ...] = ()

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.graph_id, "graph_id"),
            (self.title, "title"),
            (self.start_node_id, "start_node_id"),
        ):
            if value is not None:
                _require_non_blank(value, field_name)


@dataclass(frozen=True, slots=True)
class TutorialDraftDocument:
    """Persistable editor document containing a partial graph and capture evidence."""

    graph: DraftTutorialGraph = field(default_factory=DraftTutorialGraph)
    captures: tuple[ScreenCapture, ...] = ()

    def __post_init__(self) -> None:
        _require_unique(
            tuple(capture.capture_id for capture in self.captures),
            "capture_id",
        )


class DraftIssueCode(StrEnum):
    """Stable reasons why an editor document is not ready for promotion."""

    MISSING_GRAPH_ID = "missing_graph_id"
    MISSING_TITLE = "missing_title"
    MISSING_RECORDED_APP = "missing_recorded_app"
    MISSING_START_NODE = "missing_start_node"
    NO_NODES = "no_nodes"


@dataclass(frozen=True, slots=True)
class DraftValidationIssue:
    """One missing piece in a partially authored tutorial."""

    code: DraftIssueCode
    message: str
    path: str


class IncompleteTutorialDraft(ValueError):
    """Raised when a partial document cannot become a formal graph yet."""

    def __init__(self, issues: tuple[DraftValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


@dataclass(frozen=True, slots=True)
class TutorialDraftWorkspace:
    """Versioned editor state used for optimistic concurrency control."""

    workspace_id: str
    version: int
    document: TutorialDraftDocument
    created_at: datetime
    updated_at: datetime
    promoted_graph_id: str | None = None
    promoted_revision_number: int | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.workspace_id, "workspace_id")
        if self.version < 1:
            raise ValueError("version must be positive")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("workspace timestamps must include a timezone")
        has_graph = self.promoted_graph_id is not None
        has_revision = self.promoted_revision_number is not None
        if has_graph != has_revision:
            raise ValueError("promotion graph id and revision number must be set together")
        if self.promoted_graph_id is not None:
            _require_non_blank(self.promoted_graph_id, "promoted_graph_id")
        if self.promoted_revision_number is not None and self.promoted_revision_number < 1:
            raise ValueError("promoted_revision_number must be positive")


def build_tutorial_graph(document: TutorialDraftDocument) -> TutorialGraph:
    """Convert a complete editor document or report every missing top-level field."""
    draft = document.graph
    issues: list[DraftValidationIssue] = []
    if draft.graph_id is None:
        issues.append(
            DraftValidationIssue(
                DraftIssueCode.MISSING_GRAPH_ID,
                "graph id is required before promotion",
                "graph.graph_id",
            )
        )
    if draft.title is None:
        issues.append(
            DraftValidationIssue(
                DraftIssueCode.MISSING_TITLE,
                "title is required before promotion",
                "graph.title",
            )
        )
    if draft.recorded_app is None:
        issues.append(
            DraftValidationIssue(
                DraftIssueCode.MISSING_RECORDED_APP,
                "recorded app identity is required before promotion",
                "graph.recorded_app",
            )
        )
    if draft.start_node_id is None:
        issues.append(
            DraftValidationIssue(
                DraftIssueCode.MISSING_START_NODE,
                "start node is required before promotion",
                "graph.start_node_id",
            )
        )
    if not draft.nodes:
        issues.append(
            DraftValidationIssue(
                DraftIssueCode.NO_NODES,
                "at least one complete node is required before promotion",
                "graph.nodes",
            )
        )
    if issues:
        raise IncompleteTutorialDraft(tuple(issues))

    assert draft.graph_id is not None
    assert draft.title is not None
    assert draft.recorded_app is not None
    assert draft.start_node_id is not None
    return TutorialGraph(
        graph_id=draft.graph_id,
        title=draft.title,
        recorded_app=draft.recorded_app,
        start_node_id=draft.start_node_id,
        nodes=draft.nodes,
        transitions=draft.transitions,
    )
