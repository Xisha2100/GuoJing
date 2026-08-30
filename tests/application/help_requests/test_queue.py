from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.queue import HelpRequestQueue
from guojing.application.help_requests.service import HelpRequestService


def _request() -> HelpRequestRequest:
    image = b"\xff\xd8\xff\xd9"
    return HelpRequestRequest(
        client_request_id=uuid4(),
        intent="general_guidance",
        question="帮助我",
        image_media_type="image/jpeg",
        image_width=720,
        image_height=720,
        redaction_count=0,
        no_sensitive_content_confirmed=True,
        sanitized_sha256=sha256(image).hexdigest(),
        send_consent=True,
        sanitized_image_base64="/9j/2Q==",
    )


def test_queue_selects_oldest_received_request() -> None:
    now = [datetime(2026, 8, 30, tzinfo=UTC)]
    service = HelpRequestService(clock=lambda: now[0])
    first = service.accept(_request())
    now[0] += timedelta(seconds=1)
    second = service.accept(_request())
    service.mark_processing(second.request_id)

    selected = HelpRequestQueue(service).next_received()

    assert selected is not None
    assert selected.request_id == first.request_id
