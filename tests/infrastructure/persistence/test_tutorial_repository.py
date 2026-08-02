"""Real SQLite tests for revision and publication semantics."""

from pathlib import Path

import pytest

from guojing.application.tutorials.ports import (
    TutorialIdentityConflictError,
    TutorialNotFoundError,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import Base
from guojing.infrastructure.persistence.tutorial_repository import (
    SqlAlchemyTutorialRepository,
)
from tests.tutorial_factory import make_tutorial_graph, with_title


@pytest.fixture
def repository(tmp_path: Path) -> SqlAlchemyTutorialRepository:
    database = Database(f"sqlite:///{tmp_path / 'repository.db'}")
    Base.metadata.create_all(database.engine)
    return SqlAlchemyTutorialRepository(database)


def test_creates_immutable_revisions_and_publishes_an_explicit_one(
    repository: SqlAlchemyTutorialRepository,
) -> None:
    first_graph = make_tutorial_graph()
    second_graph = with_title(first_graph, "打开家人的聊天窗口")

    first = repository.create_revision(first_graph)
    second = repository.create_revision(second_graph)
    published = repository.publish_revision(first_graph.graph_id, first.revision_number)

    assert first.revision_number == 1
    assert second.revision_number == 2
    assert published.graph.title == first_graph.title
    assert repository.get_published(first_graph.graph_id).revision_number == 1

    republished = repository.publish_revision(first_graph.graph_id, second.revision_number)

    assert republished.graph.title == second_graph.title
    assert repository.get_published(first_graph.graph_id).revision_number == 2


def test_lists_only_published_tutorials(
    repository: SqlAlchemyTutorialRepository,
) -> None:
    published_graph = make_tutorial_graph()
    draft_only_graph = make_tutorial_graph(graph_id="wechat_send_voice", title="发送语音")
    revision = repository.create_revision(published_graph)
    repository.create_revision(draft_only_graph)
    repository.publish_revision(published_graph.graph_id, revision.revision_number)

    summaries = repository.list_published()

    assert len(summaries) == 1
    assert summaries[0].graph_id == published_graph.graph_id
    assert summaries[0].package_name == "com.tencent.mm"


def test_rejects_reusing_graph_id_for_another_package(
    repository: SqlAlchemyTutorialRepository,
) -> None:
    repository.create_revision(make_tutorial_graph())

    with pytest.raises(TutorialIdentityConflictError):
        repository.create_revision(make_tutorial_graph(package_name="com.example.other"))


def test_missing_publication_is_not_exposed(
    repository: SqlAlchemyTutorialRepository,
) -> None:
    repository.create_revision(make_tutorial_graph())

    with pytest.raises(TutorialNotFoundError):
        repository.get_published("wechat_open_family_chat")

    with pytest.raises(TutorialNotFoundError):
        repository.publish_revision("wechat_open_family_chat", 99)
