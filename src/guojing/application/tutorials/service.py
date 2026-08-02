"""Tutorial authoring and publication use cases."""

from guojing.application.tutorials.models import (
    PublishedTutorial,
    PublishedTutorialSummary,
    TutorialRevision,
)
from guojing.application.tutorials.ports import TutorialRepository
from guojing.domain.tutorials.models import TutorialGraph
from guojing.domain.tutorials.validation import require_valid_tutorial_graph


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
        return self._repository.publish_revision(graph_id, revision_number)

    def list_published(self) -> tuple[PublishedTutorialSummary, ...]:
        """Return the Android tutorial catalog."""
        return self._repository.list_published()

    def get_published(self, graph_id: str) -> PublishedTutorial:
        """Return one current Android tutorial."""
        return self._repository.get_published(graph_id)
