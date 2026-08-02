"""Real SQLite tests for editor versioning and atomic promotion."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from guojing.application.tutorial_drafts.ports import (
    TutorialDraftVersionConflictError,
    TutorialDraftWorkspaceNotFoundError,
)
from guojing.application.tutorials.ports import TutorialNotFoundError
from guojing.domain.tutorials.authoring import TutorialDraftDocument, build_tutorial_graph
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base, TutorialRevisionRecord
from guojing.infrastructure.persistence.tutorial_draft_repository import (
    SqlAlchemyTutorialDraftRepository,
)
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)
from tests.tutorial_factory import make_complete_draft_document


@pytest.fixture
def database(tmp_path: Path) -> Database:
    value = Database(f"sqlite:///{tmp_path / 'drafts.db'}")
    Base.metadata.create_all(value.engine)
    return value


def test_partial_document_can_be_created_and_replaced(database: Database) -> None:
    repository = SqlAlchemyTutorialDraftRepository(database)
    created = repository.create(TutorialDraftDocument())
    complete = make_complete_draft_document()

    updated = repository.replace(created.workspace_id, 1, complete)

    assert created.version == 1
    assert updated.version == 2
    assert repository.get(created.workspace_id).document == complete


def test_stale_replace_reports_current_version(database: Database) -> None:
    repository = SqlAlchemyTutorialDraftRepository(database)
    created = repository.create(TutorialDraftDocument())
    repository.replace(created.workspace_id, 1, make_complete_draft_document())

    with pytest.raises(TutorialDraftVersionConflictError) as captured:
        repository.replace(created.workspace_id, 1, TutorialDraftDocument())

    assert captured.value.expected_version == 1
    assert captured.value.current_version == 2


def test_missing_workspace_is_reported(database: Database) -> None:
    repository = SqlAlchemyTutorialDraftRepository(database)

    with pytest.raises(TutorialDraftWorkspaceNotFoundError):
        repository.get("missing")


def test_recent_list_returns_summary_without_document(database: Database) -> None:
    repository = SqlAlchemyTutorialDraftRepository(database)
    created = repository.create(make_complete_draft_document())

    summaries = repository.list_recent(limit=10)

    assert len(summaries) == 1
    assert summaries[0].workspace_id == created.workspace_id
    assert summaries[0].graph_id == "wechat_open_family_chat"
    assert summaries[0].title == "打开家人微信聊天"


def test_promotion_is_atomic_and_does_not_publish(database: Database) -> None:
    draft_repository = SqlAlchemyTutorialDraftRepository(database)
    tutorial_repository = SqlAlchemyTutorialRepository(database)
    document = make_complete_draft_document()
    workspace = draft_repository.create(document)

    promotion = draft_repository.promote(
        workspace.workspace_id,
        expected_version=1,
        graph=build_tutorial_graph(document),
    )

    assert promotion.workspace.version == 2
    assert promotion.workspace.promoted_revision_number == 1
    assert promotion.revision.revision_number == 1
    assert tutorial_repository.list_published() == ()
    with pytest.raises(TutorialNotFoundError):
        tutorial_repository.get_published(promotion.revision.graph.graph_id)


def test_stale_promotion_does_not_create_a_revision(database: Database) -> None:
    repository = SqlAlchemyTutorialDraftRepository(database)
    document = make_complete_draft_document()
    workspace = repository.create(document)
    repository.replace(workspace.workspace_id, 1, document)

    with pytest.raises(TutorialDraftVersionConflictError):
        repository.promote(
            workspace.workspace_id,
            expected_version=1,
            graph=build_tutorial_graph(document),
        )

    with database.new_session() as session:
        revision_count = session.scalar(select(func.count(TutorialRevisionRecord.revision_id)))
    assert revision_count == 0
