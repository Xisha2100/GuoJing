from pathlib import Path

from tests.auth_helpers import admin_api_client, login_test_admin


def test_admin_can_import_a_template_as_an_unpublished_workspace(tmp_path: Path) -> None:
    with admin_api_client(tmp_path) as (client, _database, _auth):
        headers = login_test_admin(client)
        response = client.post(
            "/api/v1/admin/tutorial-drafts/from-template/system_camera_take_photo",
            headers=headers,
        )
    assert response.status_code == 201
    assert response.json()["document"]["graph"]["graph_id"] == "system_camera_take_photo"
    assert response.json()["promoted_graph_id"] is None
