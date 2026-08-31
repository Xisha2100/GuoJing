from pathlib import Path

from tests.auth_helpers import admin_api_client, login_test_admin


def test_admin_can_list_reviewed_tutorial_templates(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        response = client.get("/api/v1/admin/tutorial-templates", headers=login_test_admin(client))
    assert response.status_code == 200
    template_ids = [item["template_id"] for item in response.json()]
    assert template_ids[0] == "system_camera_take_photo"
    assert "wechat_add_friend" in template_ids
    assert "system_view_gallery" in template_ids
    assert len(template_ids) == 14
