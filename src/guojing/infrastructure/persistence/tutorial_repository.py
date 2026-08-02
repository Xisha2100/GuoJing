"""SQLAlchemy implementation of the tutorial repository port."""

from datetime import UTC, datetime

from sqlalchemy import select

from guojing.application.tutorials.models import (
    PublishedTutorial,
    PublishedTutorialSummary,
    TutorialRevision,
)
from guojing.application.tutorials.ports import TutorialNotFoundError
from guojing.domain.tutorials.models import TutorialGraph
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import (
    TutorialPublicationRecord,
    TutorialRevisionRecord,
)
from guojing.infrastructure.persistence.tutorial_storage import (
    append_tutorial_revision,
    as_utc,
    deserialize_tutorial_graph,
)


class SqlAlchemyTutorialRepository:
    """Persist immutable graph snapshots and a movable publication pointer."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_revision(self, graph: TutorialGraph) -> TutorialRevision:
        created_at = datetime.now(UTC)
        with self._database.new_session() as session, session.begin():
            revision = append_tutorial_revision(session, graph, created_at)
        return revision

    def publish_revision(self, graph_id: str, revision_number: int) -> PublishedTutorial:
        published_at = datetime.now(UTC)
        with self._database.new_session() as session, session.begin():
            revision = session.scalar(
                select(TutorialRevisionRecord).where(
                    TutorialRevisionRecord.graph_id == graph_id,
                    TutorialRevisionRecord.revision_number == revision_number,
                )
            )
            if revision is None:
                raise TutorialNotFoundError(
                    f"tutorial {graph_id!r} revision {revision_number} does not exist"
                )

            publication = session.get(TutorialPublicationRecord, graph_id)
            if publication is None:
                publication = TutorialPublicationRecord(
                    graph_id=graph_id,
                    revision_id=revision.revision_id,
                    published_at=published_at,
                )
                session.add(publication)
            else:
                publication.revision_id = revision.revision_id
                publication.published_at = published_at

            graph = deserialize_tutorial_graph(revision.graph_json)

        return PublishedTutorial(
            graph=graph,
            revision_number=revision_number,
            published_at=published_at,
        )

    def list_published(self) -> tuple[PublishedTutorialSummary, ...]:
        statement = (
            select(TutorialRevisionRecord, TutorialPublicationRecord)
            .join(
                TutorialPublicationRecord,
                TutorialPublicationRecord.revision_id == TutorialRevisionRecord.revision_id,
            )
            .order_by(TutorialRevisionRecord.graph_id)
        )
        with self._database.new_session() as session:
            rows = session.execute(statement).all()

        summaries = []
        for revision, publication in rows:
            graph = deserialize_tutorial_graph(revision.graph_json)
            summaries.append(
                PublishedTutorialSummary(
                    graph_id=graph.graph_id,
                    title=graph.title,
                    package_name=graph.recorded_app.package_name,
                    recorded_version_name=graph.recorded_app.version_name,
                    recorded_version_code=graph.recorded_app.version_code,
                    revision_number=revision.revision_number,
                    published_at=as_utc(publication.published_at),
                )
            )
        return tuple(summaries)

    def get_published(self, graph_id: str) -> PublishedTutorial:
        statement = (
            select(TutorialRevisionRecord, TutorialPublicationRecord)
            .join(
                TutorialPublicationRecord,
                TutorialPublicationRecord.revision_id == TutorialRevisionRecord.revision_id,
            )
            .where(TutorialPublicationRecord.graph_id == graph_id)
        )
        with self._database.new_session() as session:
            row = session.execute(statement).one_or_none()

        if row is None:
            raise TutorialNotFoundError(f"published tutorial {graph_id!r} does not exist")
        revision, publication = row
        return PublishedTutorial(
            graph=deserialize_tutorial_graph(revision.graph_json),
            revision_number=revision.revision_number,
            published_at=as_utc(publication.published_at),
        )
