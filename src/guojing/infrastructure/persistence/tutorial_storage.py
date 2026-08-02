"""Shared SQL persistence operations for immutable tutorial revisions."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from guojing.application.tutorials.dto import TutorialGraphDto
from guojing.application.tutorials.models import TutorialRevision
from guojing.application.tutorials.ports import TutorialIdentityConflictError
from guojing.domain.tutorials.models import TutorialGraph
from guojing.infrastructure.persistence.models import (
    TutorialRecord,
    TutorialRevisionRecord,
)


def append_tutorial_revision(
    session: Session,
    graph: TutorialGraph,
    created_at: datetime,
) -> TutorialRevision:
    """Append one revision inside the caller's existing transaction."""
    tutorial = session.get(TutorialRecord, graph.graph_id)
    if tutorial is None:
        session.add(
            TutorialRecord(
                graph_id=graph.graph_id,
                package_name=graph.recorded_app.package_name,
                created_at=created_at,
            )
        )
        revision_number = 1
    else:
        if tutorial.package_name != graph.recorded_app.package_name:
            raise TutorialIdentityConflictError(
                f"tutorial {graph.graph_id!r} already belongs to package {tutorial.package_name!r}"
            )
        revision_number = _next_revision_number(session, graph.graph_id)

    session.add(
        TutorialRevisionRecord(
            revision_id=str(uuid4()),
            graph_id=graph.graph_id,
            revision_number=revision_number,
            graph_json=serialize_tutorial_graph(graph),
            created_at=created_at,
        )
    )
    return TutorialRevision(
        graph=graph,
        revision_number=revision_number,
        created_at=created_at,
    )


def serialize_tutorial_graph(graph: TutorialGraph) -> str:
    payload = TutorialGraphDto.from_domain(graph).model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def deserialize_tutorial_graph(payload: str) -> TutorialGraph:
    return TutorialGraphDto.model_validate_json(payload).to_domain()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _next_revision_number(session: Session, graph_id: str) -> int:
    statement = select(func.max(TutorialRevisionRecord.revision_number)).where(
        TutorialRevisionRecord.graph_id == graph_id
    )
    maximum = session.scalar(statement)
    return (maximum or 0) + 1
