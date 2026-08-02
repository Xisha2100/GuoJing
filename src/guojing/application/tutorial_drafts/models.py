"""Application results for tutorial editor workflows."""

from dataclasses import dataclass
from datetime import datetime

from guojing.application.tutorials.models import TutorialRevision
from guojing.domain.tutorials.authoring import TutorialDraftWorkspace


@dataclass(frozen=True, slots=True)
class DraftReadinessIssue:
    """One editor-facing reason that prevents promotion."""

    code: str
    message: str
    path: str | None = None
    node_id: str | None = None
    transition_id: str | None = None


@dataclass(frozen=True, slots=True)
class DraftReadiness:
    """Complete validation report for one editor document."""

    ready: bool
    issues: tuple[DraftReadinessIssue, ...]


@dataclass(frozen=True, slots=True)
class DraftPromotion:
    """A workspace update plus the formal unpublished revision it created."""

    workspace: TutorialDraftWorkspace
    revision: TutorialRevision


@dataclass(frozen=True, slots=True)
class TutorialDraftWorkspaceSummary:
    """Small recent-workspace entry for the management webpage."""

    workspace_id: str
    version: int
    graph_id: str | None
    title: str | None
    updated_at: datetime
    promoted_graph_id: str | None
    promoted_revision_number: int | None
