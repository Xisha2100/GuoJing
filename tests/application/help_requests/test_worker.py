from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.queue import HelpRequestQueue
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.help_requests.worker import HelpRequestWorker
from guojing.application.help_requests.workflow import (
    HelpRequestWorkflowStage,
    HelpRequestWorkflowState,
)


def test_worker_runs_a_bounded_pass_over_received_requests() -> None:
    image = b"\xff\xd8\xff\xd9"
    service = HelpRequestService(clock=lambda: datetime.now(UTC))
    receipt = service.accept(
        HelpRequestRequest(
            client_request_id=uuid4(),
            intent="general_guidance",
            question="帮助",
            image_media_type="image/jpeg",
            image_width=1,
            image_height=1,
            redaction_count=0,
            no_sensitive_content_confirmed=True,
            sanitized_sha256=sha256(image).hexdigest(),
            send_consent=True,
            sanitized_image_base64="/9j/2Q==",
        )
    )
    seen: list[object] = []

    def run(request_id: UUID) -> HelpRequestWorkflowState:
        seen.append(request_id)
        return cast(
            HelpRequestWorkflowState,
            type("State", (), {"stage": HelpRequestWorkflowStage.COMPLETED})(),
        )

    states = HelpRequestWorker(HelpRequestQueue(service), run).run_once(limit=1)
    assert len(states) == 1
    assert seen == [receipt.request_id]
