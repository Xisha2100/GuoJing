from pathlib import Path

from tests.auth_helpers import admin_api_client, login_test_admin


def test_admin_can_list_reviewed_tutorial_templates(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        response = client.get("/api/v1/admin/tutorial-templates", headers=login_test_admin(client))
    assert response.status_code == 200
    assert response.json() == [{"template_id": "system_camera_take_photo"}]
