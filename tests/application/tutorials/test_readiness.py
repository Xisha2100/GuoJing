from dataclasses import replace

from guojing.application.tutorials.camera_tutorial import camera_capture_tutorial
from guojing.application.tutorials.readiness import assess_readiness
from guojing.domain.tutorials.models import RiskLevel


def test_camera_vertical_slice_passes_release_readiness() -> None:
    result = assess_readiness(camera_capture_tutorial())
    assert result.ready is True
    assert result.reasons == ()


def test_non_low_risk_step_blocks_release() -> None:
    graph = camera_capture_tutorial()
    changed = replace(graph.transitions[0], risk_level=RiskLevel.SENSITIVE)
    result = assess_readiness(replace(graph, transitions=(changed,)))
    assert result.ready is False
    assert "非低风险" in result.reasons[0]
