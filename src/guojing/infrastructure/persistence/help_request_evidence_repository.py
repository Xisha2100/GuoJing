"""SQLAlchemy adapter for expiring, normalized help-request evidence."""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from guojing.domain.evidence import (
    EvidenceAnchor,
    EvidenceBounds,
    EvidenceEnvelope,
    EvidenceSharingPolicy,
    EvidenceSource,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.models import HelpRequestEvidenceRecord
from guojing.infrastructure.persistence.tutorial_storage import as_utc


class SqlAlchemyHelpRequestEvidenceRepository:
    """Store bounded evidence independently from the help-request image lifecycle."""

    def __init__(
        self,
        database: Database,
        *,
        max_envelopes: int = 1_000,
        max_envelopes_per_request: int = 8,
    ) -> None:
        if max_envelopes < 1:
            raise ValueError("max_envelopes must be positive")
        if max_envelopes_per_request < 1:
            raise ValueError("max_envelopes_per_request must be positive")
        self._database = database
        self._max_envelopes = max_envelopes
        self._max_envelopes_per_request = max_envelopes_per_request

    def save(self, envelope: EvidenceEnvelope, now: datetime) -> EvidenceEnvelope:
        with self._database.new_session() as session, session.begin():
            _purge_expired(session, now)
            record = session.get(HelpRequestEvidenceRecord, str(envelope.evidence_id))
            if record is None:
                session.add(_to_record(envelope, now))
            else:
                stored = _from_record(record)
                if not _same_submission(stored, envelope):
                    raise ValueError("evidence_id cannot be reused with different content")
                return stored
            _evict_request_excess(
                session,
                envelope.request_id,
                self._max_envelopes_per_request,
            )
            _evict_if_full(session, self._max_envelopes)
        return envelope

    def get_latest(self, request_id: UUID, now: datetime) -> EvidenceEnvelope | None:
        with self._database.new_session() as session, session.begin():
            _purge_expired(session, now)
            record = session.scalar(
                select(HelpRequestEvidenceRecord)
                .where(HelpRequestEvidenceRecord.request_id == str(request_id))
                .order_by(
                    HelpRequestEvidenceRecord.received_at.desc(),
                    HelpRequestEvidenceRecord.evidence_id.desc(),
                )
                .limit(1)
            )
            return _from_record(record) if record is not None else None


def _to_record(envelope: EvidenceEnvelope, received_at: datetime) -> HelpRequestEvidenceRecord:
    return HelpRequestEvidenceRecord(
        evidence_id=str(envelope.evidence_id),
        request_id=str(envelope.request_id),
        package_name=envelope.package_name,
        version_name=envelope.version_name,
        version_code=envelope.version_code,
        source=envelope.source.value,
        sharing_policy=envelope.sharing_policy.value,
        structure_score=envelope.structure_score,
        captured_at=envelope.captured_at,
        received_at=received_at,
        expires_at=envelope.expires_at,
        anchors_json=_serialize_anchors(envelope),
        sanitized_screenshot_sha256=envelope.sanitized_screenshot_sha256,
    )


def _from_record(record: HelpRequestEvidenceRecord) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=UUID(record.evidence_id),
        request_id=UUID(record.request_id),
        package_name=record.package_name,
        version_name=record.version_name,
        version_code=record.version_code,
        source=EvidenceSource(record.source),
        sharing_policy=EvidenceSharingPolicy(record.sharing_policy),
        structure_score=record.structure_score,
        captured_at=as_utc(record.captured_at),
        expires_at=as_utc(record.expires_at),
        anchors=_deserialize_anchors(record.anchors_json),
        sanitized_screenshot_sha256=record.sanitized_screenshot_sha256,
    )


def _serialize_anchors(envelope: EvidenceEnvelope) -> str:
    return json.dumps(
        [
            {
                "anchor_id": anchor.anchor_id,
                "confidence": anchor.confidence,
                "normalized_bounds": (
                    {
                        "left": anchor.normalized_bounds.left,
                        "top": anchor.normalized_bounds.top,
                        "right": anchor.normalized_bounds.right,
                        "bottom": anchor.normalized_bounds.bottom,
                    }
                    if anchor.normalized_bounds is not None
                    else None
                ),
            }
            for anchor in envelope.anchors
        ],
        separators=(",", ":"),
        sort_keys=True,
    )


def _deserialize_anchors(payload: str) -> tuple[EvidenceAnchor, ...]:
    values = json.loads(payload)
    return tuple(
        EvidenceAnchor(
            anchor_id=value["anchor_id"],
            confidence=value["confidence"],
            normalized_bounds=(
                EvidenceBounds(**value["normalized_bounds"])
                if value["normalized_bounds"] is not None
                else None
            ),
        )
        for value in values
    )


def _purge_expired(session: Session, now: datetime) -> None:
    session.execute(
        delete(HelpRequestEvidenceRecord).where(
            HelpRequestEvidenceRecord.expires_at <= now,
        )
    )


def _evict_if_full(session: Session, max_envelopes: int) -> None:
    records = session.scalars(
        select(HelpRequestEvidenceRecord)
        .order_by(
            HelpRequestEvidenceRecord.received_at.desc(),
            HelpRequestEvidenceRecord.evidence_id.desc(),
        )
        .offset(max_envelopes)
    ).all()
    for record in records:
        session.delete(record)


def _evict_request_excess(
    session: Session,
    request_id: UUID,
    max_envelopes_per_request: int,
) -> None:
    records = session.scalars(
        select(HelpRequestEvidenceRecord)
        .where(HelpRequestEvidenceRecord.request_id == str(request_id))
        .order_by(
            HelpRequestEvidenceRecord.received_at.desc(),
            HelpRequestEvidenceRecord.evidence_id.desc(),
        )
        .offset(max_envelopes_per_request)
    ).all()
    for record in records:
        session.delete(record)


def _same_submission(stored: EvidenceEnvelope, incoming: EvidenceEnvelope) -> bool:
    """Compare client-owned content while allowing server TTL normalization."""
    return (
        stored.evidence_id == incoming.evidence_id
        and stored.request_id == incoming.request_id
        and stored.package_name == incoming.package_name
        and stored.version_name == incoming.version_name
        and stored.version_code == incoming.version_code
        and stored.source is incoming.source
        and stored.sharing_policy is incoming.sharing_policy
        and stored.structure_score == incoming.structure_score
        and stored.captured_at == incoming.captured_at
        and stored.anchors == incoming.anchors
        and stored.sanitized_screenshot_sha256 == incoming.sanitized_screenshot_sha256
    )
