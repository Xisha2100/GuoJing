from guojing.application.tutorials.camera_tutorial import camera_capture_tutorial
from guojing.domain.tutorials.models import PrivacyMode, RiskLevel


def test_camera_tutorial_is_a_local_only_low_risk_graph() -> None:
    graph = camera_capture_tutorial()

    assert graph.graph_id == "system_camera_take_photo"
    assert all(node.privacy_mode is PrivacyMode.LOCAL_ONLY for node in graph.nodes)
    assert graph.transitions[0].risk_level is RiskLevel.LOW
    assert graph.transitions[0].target_anchor_id == "shutter_button"
