"""Reviewed tutorial templates that still require device-specific verification."""

from guojing.application.tutorials.camera_tutorial import camera_capture_tutorial
from guojing.domain.tutorials.models import TutorialGraph


class TutorialTemplateCatalog:
    """Expose stable template identifiers without making them published tutorials."""

    def available_ids(self) -> tuple[str, ...]:
        return ("system_camera_take_photo",)

    def create_draft(self, template_id: str) -> TutorialGraph:
        if template_id != "system_camera_take_photo":
            raise ValueError("unknown tutorial template")
        return camera_capture_tutorial()
