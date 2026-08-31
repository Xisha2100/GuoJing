from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from guojing.application.help_requests.dto import HelpRequestRequest
from guojing.application.help_requests.queue import HelpRequestQueue
from guojing.application.help_requests.service import HelpRequestService
from guojing.application.help_requests.worker_claim import HelpRequestWorkerClaimer


def test_worker_claim_binds_oldest_request_to_a_lease() -> None:
    image = b"\xff\xd8\xff\xd9"
    service = HelpRequestService()
    request = HelpRequestRequest(
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
    receipt = service.accept(request)
    claim = HelpRequestWorkerClaimer(HelpRequestQueue(service)).claim("worker-a", datetime.now(UTC))
    assert claim is not None
    assert claim.request.request_id == receipt.request_id
    assert claim.lease.worker_id == "worker-a"
