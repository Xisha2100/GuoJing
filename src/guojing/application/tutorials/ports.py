"""Ports required by tutorial application services."""

from typing import Protocol

from guojing.application.tutorials.models import (
    PublishedTutorial,
    PublishedTutorialSummary,
    TutorialRevision,
)
from guojing.domain.tutorials.models import TutorialGraph


class TutorialNotFoundError(LookupError):
    """Raised when a requested tutorial or revision does not exist."""


class TutorialIdentityConflictError(ValueError):
    """Raised when one graph id is reused for another Android package."""


class TutorialRepository(Protocol):
    """Persistence contract owned by the application layer."""

    def create_revision(self, graph: TutorialGraph) -> TutorialRevision:
        """Append one immutable revision."""

    def publish_revision(self, graph_id: str, revision_number: int) -> PublishedTutorial:
        """Atomically make one existing revision public."""

    def list_published(self) -> tuple[PublishedTutorialSummary, ...]:
        """List current public tutorials without their full graphs."""

    def get_published(self, graph_id: str) -> PublishedTutorial:
        """Return the current public revision."""
