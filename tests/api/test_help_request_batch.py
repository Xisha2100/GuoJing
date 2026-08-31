from pathlib import Path

from tests.api.test_help_requests import _payload
from tests.auth_helpers import admin_api_client, login_test_admin


def test_admin_can_process_a_bounded_batch(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        headers = login_test_admin(client)
        submitted = client.post(
            "/api/v1/help-requests",
            json=_payload(
                intent="general_guidance", redaction_count=0, no_sensitive_content_confirmed=True
            ),
        )
        processed = client.post(
            "/api/v1/admin/help-requests/process-next",
            headers=headers,
            json={"limit": 1},
        )
    assert submitted.status_code == 202
    assert processed.status_code == 200
    assert len(processed.json()) == 1
    assert processed.json()[0]["processing_status"] == "guidance_ready"
