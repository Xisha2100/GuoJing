import pytest

from guojing.application.tutorials.templates import TutorialTemplateCatalog


def test_camera_template_creates_a_draft_only_after_explicit_selection() -> None:
    catalog = TutorialTemplateCatalog()
    assert catalog.available_ids()[0] == "system_camera_take_photo"
    assert len(catalog.available_ids()) == 14
    assert catalog.create_draft("system_camera_take_photo").graph_id == "system_camera_take_photo"
    with pytest.raises(ValueError, match="unknown"):
        catalog.create_draft("wechat_pay")
