"""Persistence port for versioned tutorial editor workspaces."""

from typing import Protocol

from guojing.application.tutorial_drafts.models import (
    DraftPromotion,
    TutorialDraftWorkspaceSummary,
)
from guojing.domain.tutorials.authoring import (
    TutorialDraftDocument,
    TutorialDraftWorkspace,
)
from guojing.domain.tutorials.models import TutorialGraph


class TutorialDraftWorkspaceNotFoundError(LookupError):
    """Raised when an editor workspace id does not exist."""


class TutorialDraftVersionConflictError(RuntimeError):
    """Raised when a client edits an older workspace version."""

    def __init__(self, expected_version: int, current_version: int) -> None:
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"workspace version conflict: expected {expected_version}, current {current_version}"
        )


class TutorialDraftRepository(Protocol):
    """Atomic storage operations required by the authoring service."""

    def create(self, document: TutorialDraftDocument) -> TutorialDraftWorkspace:
        """Create a new workspace at version one."""

    def get(self, workspace_id: str) -> TutorialDraftWorkspace:
        """Read one editor workspace."""

    def list_recent(self, limit: int) -> tuple[TutorialDraftWorkspaceSummary, ...]:
        """List recent workspaces without their full documents."""

    def replace(
        self,
        workspace_id: str,
        expected_version: int,
        document: TutorialDraftDocument,
    ) -> TutorialDraftWorkspace:
        """Replace the document only when the expected version is current."""

    def promote(
        self,
        workspace_id: str,
        expected_version: int,
        graph: TutorialGraph,
    ) -> DraftPromotion:
        """Atomically append a formal revision and record it on the workspace."""
