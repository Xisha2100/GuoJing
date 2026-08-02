"""SQLAlchemy adapter for versioned tutorial editor workspaces."""

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from guojing.application.tutorial_drafts.dto import TutorialDraftDocumentDto
from guojing.application.tutorial_drafts.models import (
    DraftPromotion,
    TutorialDraftWorkspaceSummary,
)
from guojing.application.tutorial_drafts.ports import (
    TutorialDraftVersionConflictError,
    TutorialDraftWorkspaceNotFoundError,
)
from guojing.domain.tutorials.authoring import (
    TutorialDraftDocument,
    TutorialDraftWorkspace,
)
from guojing.domain.tutorials.models import TutorialGraph
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import TutorialDraftWorkspaceRecord
from guojing.infrastructure.persistence.tutorial_storage import (
    append_tutorial_revision,
    as_utc,
)


class SqlAlchemyTutorialDraftRepository:
    """Store whole editor documents and guard every mutation by version."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, document: TutorialDraftDocument) -> TutorialDraftWorkspace:
        now = datetime.now(UTC)
        record = TutorialDraftWorkspaceRecord(
            workspace_id=str(uuid4()),
            version=1,
            document_json=_serialize_document(document),
            promoted_graph_id=None,
            promoted_revision_number=None,
            created_at=now,
            updated_at=now,
        )
        with self._database.new_session() as session, session.begin():
            session.add(record)
        return _to_workspace(record)

    def get(self, workspace_id: str) -> TutorialDraftWorkspace:
        with self._database.new_session() as session:
            record = session.get(TutorialDraftWorkspaceRecord, workspace_id)
            if record is None:
                raise TutorialDraftWorkspaceNotFoundError(
                    f"tutorial draft workspace {workspace_id!r} does not exist"
                )
            return _to_workspace(record)

    def list_recent(self, limit: int) -> tuple[TutorialDraftWorkspaceSummary, ...]:
        statement = (
            select(TutorialDraftWorkspaceRecord)
            .order_by(TutorialDraftWorkspaceRecord.updated_at.desc())
            .limit(limit)
        )
        with self._database.new_session() as session:
            records = session.scalars(statement).all()
        summaries = []
        for record in records:
            graph = _deserialize_document(record.document_json).graph
            summaries.append(
                TutorialDraftWorkspaceSummary(
                    workspace_id=record.workspace_id,
                    version=record.version,
                    graph_id=graph.graph_id,
                    title=graph.title,
                    updated_at=as_utc(record.updated_at),
                    promoted_graph_id=record.promoted_graph_id,
                    promoted_revision_number=record.promoted_revision_number,
                )
            )
        return tuple(summaries)

    def replace(
        self,
        workspace_id: str,
        expected_version: int,
        document: TutorialDraftDocument,
    ) -> TutorialDraftWorkspace:
        now = datetime.now(UTC)
        with self._database.new_session() as session, session.begin():
            current = _get_current(session, workspace_id)
            result = session.execute(
                update(TutorialDraftWorkspaceRecord)
                .where(
                    TutorialDraftWorkspaceRecord.workspace_id == workspace_id,
                    TutorialDraftWorkspaceRecord.version == expected_version,
                )
                .values(
                    version=expected_version + 1,
                    document_json=_serialize_document(document),
                    updated_at=now,
                )
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                _raise_version_conflict(current, expected_version)

        return TutorialDraftWorkspace(
            workspace_id=workspace_id,
            version=expected_version + 1,
            document=document,
            created_at=as_utc(current.created_at),
            updated_at=now,
            promoted_graph_id=current.promoted_graph_id,
            promoted_revision_number=current.promoted_revision_number,
        )

    def promote(
        self,
        workspace_id: str,
        expected_version: int,
        graph: TutorialGraph,
    ) -> DraftPromotion:
        now = datetime.now(UTC)
        with self._database.new_session() as session, session.begin():
            current = _get_current(session, workspace_id)
            if current.version != expected_version:
                _raise_version_conflict(current, expected_version)
            revision = append_tutorial_revision(session, graph, now)
            result = session.execute(
                update(TutorialDraftWorkspaceRecord)
                .where(
                    TutorialDraftWorkspaceRecord.workspace_id == workspace_id,
                    TutorialDraftWorkspaceRecord.version == expected_version,
                )
                .values(
                    version=expected_version + 1,
                    promoted_graph_id=graph.graph_id,
                    promoted_revision_number=revision.revision_number,
                    updated_at=now,
                )
            )
            if cast(CursorResult[Any], result).rowcount != 1:
                _raise_version_conflict(current, expected_version)

        workspace = TutorialDraftWorkspace(
            workspace_id=workspace_id,
            version=expected_version + 1,
            document=_deserialize_document(current.document_json),
            created_at=as_utc(current.created_at),
            updated_at=now,
            promoted_graph_id=graph.graph_id,
            promoted_revision_number=revision.revision_number,
        )
        return DraftPromotion(workspace=workspace, revision=revision)


def _get_current(session: Session, workspace_id: str) -> TutorialDraftWorkspaceRecord:
    current = session.get(TutorialDraftWorkspaceRecord, workspace_id)
    if current is None:
        raise TutorialDraftWorkspaceNotFoundError(
            f"tutorial draft workspace {workspace_id!r} does not exist"
        )
    return current


def _raise_version_conflict(
    current: TutorialDraftWorkspaceRecord,
    expected_version: int,
) -> None:
    raise TutorialDraftVersionConflictError(
        expected_version=expected_version,
        current_version=current.version,
    )


def _serialize_document(document: TutorialDraftDocument) -> str:
    payload = TutorialDraftDocumentDto.from_domain(document).model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _deserialize_document(payload: str) -> TutorialDraftDocument:
    return TutorialDraftDocumentDto.model_validate_json(payload).to_domain()


def _to_workspace(record: TutorialDraftWorkspaceRecord) -> TutorialDraftWorkspace:
    return TutorialDraftWorkspace(
        workspace_id=record.workspace_id,
        version=record.version,
        document=_deserialize_document(record.document_json),
        created_at=as_utc(record.created_at),
        updated_at=as_utc(record.updated_at),
        promoted_graph_id=record.promoted_graph_id,
        promoted_revision_number=record.promoted_revision_number,
    )
