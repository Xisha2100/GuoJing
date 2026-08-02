"""Use cases for incremental authoring and explicit promotion."""

from guojing.application.tutorial_drafts.models import (
    DraftPromotion,
    DraftReadiness,
    DraftReadinessIssue,
    TutorialDraftWorkspaceSummary,
)
from guojing.application.tutorial_drafts.ports import (
    TutorialDraftRepository,
    TutorialDraftVersionConflictError,
)
from guojing.domain.tutorials.authoring import (
    IncompleteTutorialDraft,
    TutorialDraftDocument,
    TutorialDraftWorkspace,
    build_tutorial_graph,
)
from guojing.domain.tutorials.validation import (
    InvalidTutorialGraph,
    validate_tutorial_graph,
)


class TutorialDraftService:
    """Coordinate partial saves, validation, and non-publishing promotion."""

    def __init__(self, repository: TutorialDraftRepository) -> None:
        self._repository = repository

    def create(self, document: TutorialDraftDocument) -> TutorialDraftWorkspace:
        return self._repository.create(document)

    def get(self, workspace_id: str) -> TutorialDraftWorkspace:
        return self._repository.get(workspace_id)

    def list_recent(self, limit: int = 50) -> tuple[TutorialDraftWorkspaceSummary, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        return self._repository.list_recent(limit)

    def replace(
        self,
        workspace_id: str,
        expected_version: int,
        document: TutorialDraftDocument,
    ) -> TutorialDraftWorkspace:
        if expected_version < 1:
            raise ValueError("expected_version must be positive")
        return self._repository.replace(workspace_id, expected_version, document)

    def validate(self, document: TutorialDraftDocument) -> DraftReadiness:
        """Report completeness first, then every structural graph issue."""
        try:
            graph = build_tutorial_graph(document)
        except IncompleteTutorialDraft as error:
            return DraftReadiness(
                ready=False,
                issues=tuple(
                    DraftReadinessIssue(
                        code=issue.code.value,
                        message=issue.message,
                        path=issue.path,
                    )
                    for issue in error.issues
                ),
            )

        graph_issues = validate_tutorial_graph(graph)
        return DraftReadiness(
            ready=not graph_issues,
            issues=tuple(
                DraftReadinessIssue(
                    code=issue.code.value,
                    message=issue.message,
                    node_id=issue.node_id,
                    transition_id=issue.transition_id,
                )
                for issue in graph_issues
            ),
        )

    def promote(self, workspace_id: str, expected_version: int) -> DraftPromotion:
        """Create an unpublished formal revision from the exact expected workspace."""
        if expected_version < 1:
            raise ValueError("expected_version must be positive")
        workspace = self._repository.get(workspace_id)
        if workspace.version != expected_version:
            raise TutorialDraftVersionConflictError(
                expected_version=expected_version,
                current_version=workspace.version,
            )
        graph = build_tutorial_graph(workspace.document)
        issues = validate_tutorial_graph(graph)
        if issues:
            raise InvalidTutorialGraph(issues)
        return self._repository.promote(workspace_id, expected_version, graph)
