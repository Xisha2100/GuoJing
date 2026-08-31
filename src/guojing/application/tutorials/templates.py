"""Reviewed tutorial templates that still require device-specific verification."""

from guojing.application.tutorials.camera_tutorial import camera_capture_tutorial
from guojing.application.tutorials.scenario_templates import MVP_SCENARIOS, scenario_template
from guojing.domain.tutorials.models import TutorialGraph


class TutorialTemplateCatalog:
    """Expose stable template identifiers without making them published tutorials."""

    def available_ids(self) -> tuple[str, ...]:
        return ("system_camera_take_photo", *(value.template_id for value in MVP_SCENARIOS))

    def create_draft(self, template_id: str) -> TutorialGraph:
        if template_id != "system_camera_take_photo":
            return scenario_template(template_id)
        return camera_capture_tutorial()
