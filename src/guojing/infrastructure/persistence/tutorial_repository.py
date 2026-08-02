"""SQLAlchemy implementation of the tutorial repository port."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from guojing.application.tutorials.dto import TutorialGraphDto
from guojing.application.tutorials.models import (
    PublishedTutorial,
    PublishedTutorialSummary,
    TutorialRevision,
)
from guojing.application.tutorials.ports import (
    TutorialIdentityConflictError,
    TutorialNotFoundError,
)
from guojing.domain.tutorials.models import TutorialGraph
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import (
    TutorialPublicationRecord,
    TutorialRecord,
    TutorialRevisionRecord,
)


class SqlAlchemyTutorialRepository:
    """Persist immutable graph snapshots and a movable publication pointer."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_revision(self, graph: TutorialGraph) -> TutorialRevision:
        created_at = datetime.now(UTC)
        with self._database.new_session() as session, session.begin():
            tutorial = session.get(TutorialRecord, graph.graph_id)
            if tutorial is None:
                tutorial = TutorialRecord(
                    graph_id=graph.graph_id,
                    package_name=graph.recorded_app.package_name,
                    created_at=created_at,
                )
                session.add(tutorial)
                revision_number = 1
            else:
                if tutorial.package_name != graph.recorded_app.package_name:
                    raise TutorialIdentityConflictError(
                        f"tutorial {graph.graph_id!r} already belongs to package "
                        f"{tutorial.package_name!r}"
                    )
                revision_number = self._next_revision_number(graph.graph_id, session)

            session.add(
                TutorialRevisionRecord(
                    revision_id=str(uuid4()),
                    graph_id=graph.graph_id,
                    revision_number=revision_number,
                    graph_json=_serialize_graph(graph),
                    created_at=created_at,
                )
            )

        return TutorialRevision(
            graph=graph,
            revision_number=revision_number,
            created_at=created_at,
        )

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

            graph = _deserialize_graph(revision.graph_json)

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
            graph = _deserialize_graph(revision.graph_json)
            summaries.append(
                PublishedTutorialSummary(
                    graph_id=graph.graph_id,
                    title=graph.title,
                    package_name=graph.recorded_app.package_name,
                    recorded_version_name=graph.recorded_app.version_name,
                    recorded_version_code=graph.recorded_app.version_code,
                    revision_number=revision.revision_number,
                    published_at=_as_utc(publication.published_at),
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
            graph=_deserialize_graph(revision.graph_json),
            revision_number=revision.revision_number,
            published_at=_as_utc(publication.published_at),
        )

    @staticmethod
    def _next_revision_number(graph_id: str, session: Session) -> int:
        statement = select(func.max(TutorialRevisionRecord.revision_number)).where(
            TutorialRevisionRecord.graph_id == graph_id
        )
        maximum = session.scalar(statement)
        return (maximum or 0) + 1


def _serialize_graph(graph: TutorialGraph) -> str:
    payload = TutorialGraphDto.from_domain(graph).model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _deserialize_graph(payload: str) -> TutorialGraph:
    return TutorialGraphDto.model_validate_json(payload).to_domain()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
