"""Tutorial authoring and publication use cases."""

from typing import Protocol, cast

from guojing.application.tutorials.models import (
    PublishedTutorial,
    PublishedTutorialSummary,
    TutorialRevision,
)
from guojing.application.tutorials.ports import TutorialRepository
from guojing.application.tutorials.readiness import assess_readiness
from guojing.domain.tutorials.models import TutorialGraph
from guojing.domain.tutorials.validation import require_valid_tutorial_graph


class _TutorialRevisionReader(Protocol):
    def get_revision(self, graph_id: str, revision_number: int) -> TutorialRevision: ...


class TutorialService:
    """Apply domain policy before delegating persistence."""

    def __init__(self, repository: TutorialRepository) -> None:
        self._repository = repository

    def save_draft(self, graph: TutorialGraph) -> TutorialRevision:
        """Validate and append a tutorial revision."""
        require_valid_tutorial_graph(graph)
        return self._repository.create_revision(graph)

    def publish(self, graph_id: str, revision_number: int) -> PublishedTutorial:
        """Publish an explicitly selected revision."""
        if revision_number < 1:
            raise ValueError("revision_number must be positive")
        reader = cast(_TutorialRevisionReader, self._repository)
        revision = reader.get_revision(graph_id, revision_number)
        readiness = assess_readiness(revision.graph)
        if not readiness.ready:
            raise ValueError(
                "tutorial revision is not release-ready: " + "; ".join(readiness.reasons)
            )
        return self._repository.publish_revision(graph_id, revision_number)

    def list_published(self) -> tuple[PublishedTutorialSummary, ...]:
        """Return the Android tutorial catalog."""
        return self._repository.list_published()

    def list_published_for_package(self, package_name: str) -> tuple[PublishedTutorial, ...]:
        """Load current published graphs for one exact Android package."""
        if not package_name.strip():
            raise ValueError("package_name must not be blank")
        summaries = (
            summary
            for summary in self._repository.list_published()
            if summary.package_name == package_name
        )
        return tuple(self._repository.get_published(summary.graph_id) for summary in summaries)

    def get_published(self, graph_id: str) -> PublishedTutorial:
        """Return one current Android tutorial."""
        return self._repository.get_published(graph_id)
