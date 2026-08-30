"""SQLite persistence and TTL behavior for module 21."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.ports import HelpRequestStateConflictError
from guojing.application.help_requests.service import HelpRequestNotFound, HelpRequestService
from guojing.domain.help_requests import (
    HelpRequestGuidance,
    HelpRequestGuidanceStep,
    HelpRequestProcessingStatus,
    HelpRequestTutorialMatch,
    HelpRequestTutorialPlan,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.persistence.help_request_repository import (
    SqlAlchemyHelpRequestRepository,
)
from guojing.infrastructure.persistence.models import Base


def _request(
    client_request_id: UUID | None = None,
    *,
    intent: str = "general_guidance",
) -> HelpRequestRequest:
    image = b"\xff\xd8\xff\xd9"
    return HelpRequestRequest(
        client_request_id=client_request_id or uuid4(),
        intent=intent,
        question="这个页面下一步怎么做?",
        image_media_type="image/jpeg",
        image_width=720,
        image_height=1_440,
        redaction_count=0,
        no_sensitive_content_confirmed=True,
        sanitized_sha256=sha256(image).hexdigest(),
        send_consent=True,
        sanitized_image_base64="/9j/2Q==",
    )


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'help.db'}")
    Base.metadata.create_all(database.engine)
    return database


def test_result_survives_a_new_service_instance(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    database = _database(tmp_path)
    repository = SqlAlchemyHelpRequestRepository(database)
    first_service = HelpRequestService(
        clock=lambda: now,
        repository=repository,
        result_ttl=timedelta(hours=2),
    )

    receipt = first_service.accept(_request())
    second_service = HelpRequestService(
        clock=lambda: now + timedelta(minutes=1),
        repository=SqlAlchemyHelpRequestRepository(database),
    )

    result = second_service.get_result(receipt.request_id)

    assert result.request_id == receipt.request_id
    assert result.processing_status is HelpRequestProcessingStatus.RECEIVED
    database.dispose()


def test_expired_results_are_purged_on_read(tmp_path: Path) -> None:
    current = [datetime(2026, 8, 30, 8, 0, tzinfo=UTC)]
    database = _database(tmp_path)
    service = HelpRequestService(
        clock=lambda: current[0],
        repository=SqlAlchemyHelpRequestRepository(database),
        result_ttl=timedelta(hours=1),
    )
    receipt = service.accept(_request())
    current[0] += timedelta(hours=1, seconds=1)

    with pytest.raises(HelpRequestNotFound):
        service.get_result(receipt.request_id)
    database.dispose()


def test_guidance_round_trips_through_sqlite(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    database = _database(tmp_path)
    repository = SqlAlchemyHelpRequestRepository(database)
    service = HelpRequestService(clock=lambda: now, repository=repository)
    receipt = service.accept(_request())
    service.mark_processing(receipt.request_id)
    guidance = HelpRequestGuidance(
        title="基础指引",
        steps=(
            HelpRequestGuidanceStep(
                step_id="look",
                title="看标题",
                instruction="请你亲自确认页面顶部的标题。",
            ),
        ),
    )
    service.publish_guidance(receipt.request_id, guidance)

    result = HelpRequestService(
        clock=lambda: now,
        repository=SqlAlchemyHelpRequestRepository(database),
    ).get_result(receipt.request_id)

    assert result.guidance == guidance
    assert result.processing_status is HelpRequestProcessingStatus.GUIDANCE_READY
    database.dispose()


def test_idempotency_survives_a_new_service_instance(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    database = _database(tmp_path)
    client_id = uuid4()
    first = HelpRequestService(
        clock=lambda: now,
        repository=SqlAlchemyHelpRequestRepository(database),
    ).accept(_request(client_id))

    second = HelpRequestService(
        clock=lambda: now + timedelta(seconds=1),
        repository=SqlAlchemyHelpRequestRepository(database),
    ).accept(_request(client_id))

    assert second.request_id == first.request_id
    database.dispose()


def test_tutorial_checkpoint_round_trips_through_sqlite(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    database = _database(tmp_path)
    repository = SqlAlchemyHelpRequestRepository(database)
    service = HelpRequestService(clock=lambda: now, repository=repository)
    receipt = service.accept(_request(intent="recorded_tutorial"))
    service.mark_processing(receipt.request_id, workflow_stage="awaiting_evidence")
    service.mark_needs_human_review(
        receipt.request_id,
        "教程页面已匹配,请人工确认版本和步骤后发布安全说明。",
        workflow_stage="tutorial_matched",
        tutorial_match=HelpRequestTutorialMatch(
            status="matched",
            reason="strong_match",
            graph_id="wechat_open_family_chat",
            node_id="chat_list",
            revision_number=1,
        ),
        tutorial_plan=HelpRequestTutorialPlan(
            graph_id="wechat_open_family_chat",
            node_id="chat_list",
            revision_number=1,
            compatibility_status="verified",
            allowed_transition_ids=("open_family_chat",),
        ),
    )

    result = HelpRequestService(
        clock=lambda: now,
        repository=SqlAlchemyHelpRequestRepository(database),
    ).get_result(receipt.request_id)

    assert result.workflow_stage == "tutorial_matched"
    assert result.tutorial_match == HelpRequestTutorialMatch(
        status="matched",
        reason="strong_match",
        graph_id="wechat_open_family_chat",
        node_id="chat_list",
        revision_number=1,
    )
    assert result.tutorial_plan == HelpRequestTutorialPlan(
        graph_id="wechat_open_family_chat",
        node_id="chat_list",
        revision_number=1,
        compatibility_status="verified",
        allowed_transition_ids=("open_family_chat",),
    )
    database.dispose()


def test_stale_worker_cannot_overwrite_a_newer_sql_result(tmp_path: Path) -> None:
    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    database = _database(tmp_path)
    repository = SqlAlchemyHelpRequestRepository(database)
    service = HelpRequestService(clock=lambda: now, repository=repository)
    receipt = service.accept(_request())
    first_snapshot = repository.get(receipt.request_id, now)
    second_snapshot = repository.get(receipt.request_id, now)

    assert first_snapshot is not None
    assert second_snapshot is not None
    first_update = first_snapshot.transition(HelpRequestProcessingStatus.PROCESSING, now)
    repository.save(first_update, first_snapshot.state_version, now)

    stale_update = second_snapshot.transition(HelpRequestProcessingStatus.PROCESSING, now)
    with pytest.raises(HelpRequestStateConflictError, match="another worker"):
        repository.save(stale_update, second_snapshot.state_version, now)

    stored = repository.get(receipt.request_id, now)
    assert stored is not None
    assert stored.processing_status is HelpRequestProcessingStatus.PROCESSING
    assert stored.state_version == 2
    database.dispose()
