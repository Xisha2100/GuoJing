"""SQLAlchemy Repository for TTL-bound help-request result metadata."""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from guojing.application.help_requests.ports import (
    ClientRequestConflictError,
    HelpRequestCapacityError,
    HelpRequestStateConflictError,
)
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestGuidanceStep,
    HelpRequestIntent,
    HelpRequestProcessingRoute,
    HelpRequestProcessingStatus,
    HelpRequestResult,
    HelpRequestTutorialMatch,
    HelpRequestTutorialPlan,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import HelpRequestResultRecord
from guojing.infrastructure.persistence.tutorial_storage import as_utc


class SqlAlchemyHelpRequestRepository:
    """Persist only the status projection and bounded review content."""

    def __init__(self, database: Database, *, max_results: int = 1_000) -> None:
        if max_results < 1:
            raise ValueError("max_results must be positive")
        self._database = database
        self._max_results = max_results

    def create_or_get(
        self,
        result: HelpRequestResult,
        fingerprint: str,
        expires_at: datetime,
        access_token_digest: str,
        now: datetime,
    ) -> HelpRequestResult:
        try:
            with self._database.new_session() as session, session.begin():
                _purge_expired(session, now)
                existing = session.scalar(
                    select(HelpRequestResultRecord).where(
                        HelpRequestResultRecord.client_request_id == str(result.client_request_id),
                    )
                )
                if existing is not None:
                    existing_result = _existing_or_conflict(existing, fingerprint)
                    _append_access_token_digest(existing, access_token_digest)
                    return existing_result
                session.add(_to_record(result, fingerprint, expires_at, access_token_digest))
                session.flush()
                _evict_if_full(session, self._max_results)
        except IntegrityError as error:
            # A concurrent idempotent submission may win the unique-key race.
            # Re-open a transaction and append this receipt's digest so either
            # caller can finish polling even when responses arrive out of order.
            with self._database.new_session() as session, session.begin():
                _purge_expired(session, now)
                existing = session.scalar(
                    select(HelpRequestResultRecord).where(
                        HelpRequestResultRecord.client_request_id == str(result.client_request_id),
                    )
                )
                if existing is not None:
                    existing_result = _existing_or_conflict(existing, fingerprint)
                    _append_access_token_digest(existing, access_token_digest)
                    return existing_result
            raise error
        return result

    def get(self, request_id: UUID, now: datetime) -> HelpRequestResult | None:
        with self._database.new_session() as session, session.begin():
            _purge_expired(session, now)
            record = session.get(HelpRequestResultRecord, str(request_id))
            return _from_record(record) if record is not None else None

    def is_access_authorized(
        self,
        request_id: UUID,
        access_token_digest: str,
        now: datetime,
    ) -> bool:
        with self._database.new_session() as session, session.begin():
            _purge_expired(session, now)
            record = session.get(HelpRequestResultRecord, str(request_id))
            return record is not None and access_token_digest in _access_token_digests(record)

    def list(
        self,
        status: HelpRequestProcessingStatus | None,
        now: datetime,
    ) -> tuple[HelpRequestResult, ...]:
        with self._database.new_session() as session, session.begin():
            _purge_expired(session, now)
            statement = select(HelpRequestResultRecord).order_by(
                HelpRequestResultRecord.updated_at.desc(),
            )
            if status is not None:
                statement = statement.where(
                    HelpRequestResultRecord.processing_status == status.value,
                )
            records = session.scalars(statement).all()
            return tuple(_from_record(record) for record in records)

    def save(self, result: HelpRequestResult, expected_version: int, now: datetime) -> None:
        if result.state_version != expected_version + 1:
            raise ValueError("state transition must increment state_version by one")
        with self._database.new_session() as session, session.begin():
            _purge_expired(session, now)
            updated = session.execute(
                update(HelpRequestResultRecord)
                .where(
                    HelpRequestResultRecord.request_id == str(result.request_id),
                    HelpRequestResultRecord.state_version == expected_version,
                )
                .values(**_transition_values(result))
            )
            if getattr(updated, "rowcount", None) != 1:
                raise HelpRequestStateConflictError(
                    "help request result was updated by another worker",
                )


def _to_record(
    result: HelpRequestResult,
    fingerprint: str,
    expires_at: datetime,
    access_token_digest: str,
) -> HelpRequestResultRecord:
    return HelpRequestResultRecord(
        request_id=str(result.request_id),
        client_request_id=str(result.client_request_id),
        request_fingerprint=fingerprint,
        access_token_digest=access_token_digest,
        access_token_digests_json=json.dumps([access_token_digest]),
        intent=result.intent.value,
        question=result.question,
        processing_route=result.processing_route.value,
        processing_status=result.processing_status.value,
        received_at=result.received_at,
        updated_at=result.updated_at,
        state_version=result.state_version,
        expires_at=expires_at,
        guidance_json=_serialize_guidance(result.guidance),
        human_review_reason=result.human_review_reason,
        workflow_stage=result.workflow_stage,
        tutorial_match_status=(
            result.tutorial_match.status if result.tutorial_match is not None else None
        ),
        tutorial_match_reason=(
            result.tutorial_match.reason if result.tutorial_match is not None else None
        ),
        tutorial_graph_id=(
            result.tutorial_match.graph_id if result.tutorial_match is not None else None
        ),
        tutorial_node_id=(
            result.tutorial_match.node_id if result.tutorial_match is not None else None
        ),
        tutorial_revision_number=(
            result.tutorial_match.revision_number if result.tutorial_match is not None else None
        ),
        tutorial_plan_json=_serialize_tutorial_plan(result.tutorial_plan),
    )


def _from_record(record: HelpRequestResultRecord) -> HelpRequestResult:
    guidance = _deserialize_guidance(record.guidance_json)
    tutorial_match = _deserialize_tutorial_match(record)
    tutorial_plan = _deserialize_tutorial_plan(record.tutorial_plan_json)
    return HelpRequestResult(
        request_id=UUID(record.request_id),
        client_request_id=UUID(record.client_request_id),
        intent=HelpRequestIntent(record.intent),
        processing_route=HelpRequestProcessingRoute(record.processing_route),
        processing_status=HelpRequestProcessingStatus(record.processing_status),
        received_at=as_utc(record.received_at),
        updated_at=as_utc(record.updated_at),
        question=record.question,
        state_version=record.state_version,
        guidance=guidance,
        human_review_reason=record.human_review_reason,
        workflow_stage=record.workflow_stage,
        tutorial_match=tutorial_match,
        tutorial_plan=tutorial_plan,
    )


def _deserialize_tutorial_match(
    record: HelpRequestResultRecord,
) -> HelpRequestTutorialMatch | None:
    values = (
        record.tutorial_match_status,
        record.tutorial_match_reason,
        record.tutorial_graph_id,
        record.tutorial_node_id,
        record.tutorial_revision_number,
    )
    if all(value is None for value in values):
        return None
    if record.tutorial_match_status is None or record.tutorial_match_reason is None:
        raise ValueError("stored tutorial match checkpoint is incomplete")
    return HelpRequestTutorialMatch(
        status=record.tutorial_match_status,
        reason=record.tutorial_match_reason,
        graph_id=record.tutorial_graph_id,
        node_id=record.tutorial_node_id,
        revision_number=record.tutorial_revision_number,
    )


def _serialize_tutorial_plan(plan: HelpRequestTutorialPlan | None) -> str | None:
    if plan is None:
        return None
    return json.dumps(
        {
            "graph_id": plan.graph_id,
            "node_id": plan.node_id,
            "revision_number": plan.revision_number,
            "compatibility_status": plan.compatibility_status,
            "allowed_transition_ids": plan.allowed_transition_ids,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _deserialize_tutorial_plan(payload: str | None) -> HelpRequestTutorialPlan | None:
    if payload is None:
        return None
    decoded = json.loads(payload)
    transition_ids = decoded.get("allowed_transition_ids")
    if not isinstance(transition_ids, list) or not all(
        isinstance(value, str) for value in transition_ids
    ):
        raise ValueError("stored tutorial plan transition ids are invalid")
    return HelpRequestTutorialPlan(
        graph_id=decoded["graph_id"],
        node_id=decoded["node_id"],
        revision_number=decoded["revision_number"],
        compatibility_status=decoded["compatibility_status"],
        allowed_transition_ids=tuple(transition_ids),
    )


def _transition_values(result: HelpRequestResult) -> dict[str, object]:
    """Map the mutable projection fields used by the compare-and-swap update."""
    return {
        "processing_status": result.processing_status.value,
        "updated_at": result.updated_at,
        "state_version": result.state_version,
        "guidance_json": _serialize_guidance(result.guidance),
        "human_review_reason": result.human_review_reason,
        "workflow_stage": result.workflow_stage,
        "tutorial_match_status": (
            result.tutorial_match.status if result.tutorial_match is not None else None
        ),
        "tutorial_match_reason": (
            result.tutorial_match.reason if result.tutorial_match is not None else None
        ),
        "tutorial_graph_id": (
            result.tutorial_match.graph_id if result.tutorial_match is not None else None
        ),
        "tutorial_node_id": (
            result.tutorial_match.node_id if result.tutorial_match is not None else None
        ),
        "tutorial_revision_number": (
            result.tutorial_match.revision_number if result.tutorial_match is not None else None
        ),
        "tutorial_plan_json": _serialize_tutorial_plan(result.tutorial_plan),
    }


def _serialize_guidance(guidance: HelpRequestGuidance | None) -> str | None:
    if guidance is None:
        return None
    return json.dumps(
        {
            "title": guidance.title,
            "steps": [
                {
                    "step_id": step.step_id,
                    "title": step.title,
                    "instruction": step.instruction,
                    "requires_manual_action": step.requires_manual_action,
                }
                for step in guidance.steps
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _deserialize_guidance(payload: str | None) -> HelpRequestGuidance | None:
    if payload is None:
        return None
    decoded = json.loads(payload)
    steps = tuple(
        HelpRequestGuidanceStep(
            step_id=step["step_id"],
            title=step["title"],
            instruction=step["instruction"],
            requires_manual_action=step["requires_manual_action"],
        )
        for step in decoded["steps"]
    )
    return HelpRequestGuidance(title=decoded["title"], steps=steps)


def _existing_or_conflict(
    record: HelpRequestResultRecord,
    fingerprint: str,
) -> HelpRequestResult:
    if record.request_fingerprint != fingerprint:
        raise ClientRequestConflictError(
            "client_request_id cannot be reused for different request data",
        )
    return _from_record(record)


def _append_access_token_digest(
    record: HelpRequestResultRecord,
    digest: str,
    *,
    limit: int = 8,
) -> None:
    digests = _access_token_digests(record)
    if digest not in digests:
        digests = (*digests, digest)[-limit:]
    record.access_token_digest = digests[-1]
    record.access_token_digests_json = json.dumps(
        list(digests), ensure_ascii=False, separators=(",", ":")
    )


def _access_token_digests(record: HelpRequestResultRecord) -> tuple[str, ...]:
    if record.access_token_digests_json:
        try:
            values = json.loads(record.access_token_digests_json)
        except json.JSONDecodeError:
            values = []
        if isinstance(values, list) and all(isinstance(value, str) for value in values):
            return tuple(values)
    return (record.access_token_digest,)


def _purge_expired(session: Session, now: datetime) -> None:
    session.execute(
        delete(HelpRequestResultRecord).where(
            HelpRequestResultRecord.expires_at <= now,
        )
    )


def _evict_if_full(session: Session, max_results: int) -> None:
    count = session.scalar(select(func.count(HelpRequestResultRecord.request_id))) or 0
    if count <= max_results:
        return
    excess = count - max_results
    oldest = session.scalars(
        select(HelpRequestResultRecord)
        .where(
            HelpRequestResultRecord.processing_status
            == HelpRequestProcessingStatus.GUIDANCE_READY.value,
        )
        .order_by(HelpRequestResultRecord.updated_at.asc())
        .limit(excess)
    ).all()
    if len(oldest) < excess:
        raise HelpRequestCapacityError(
            "help request capacity is full; active requests are never evicted",
        )
    for record in oldest:
        session.delete(record)
