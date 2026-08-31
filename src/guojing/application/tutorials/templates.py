"""Reviewed tutorial templates that still require device-specific verification."""

from guojing.application.tutorials.camera_tutorial import camera_capture_tutorial
from guojing.application.tutorials.scenario_templates import MVP_SCENARIOS, scenario_template
from guojing.domain.tutorials.authoring import DraftTutorialGraph, TutorialDraftDocument
from guojing.domain.tutorials.models import TutorialGraph


class TutorialTemplateCatalog:
    """Expose stable template identifiers without making them published tutorials."""

    def available_ids(self) -> tuple[str, ...]:
        return ("system_camera_take_photo", *(value.template_id for value in MVP_SCENARIOS))

    def create_draft(self, template_id: str) -> TutorialGraph:
        if template_id != "system_camera_take_photo":
            return scenario_template(template_id)
        return camera_capture_tutorial()

    def create_document(self, template_id: str) -> TutorialDraftDocument:
        graph = self.create_draft(template_id)
        return TutorialDraftDocument(
            graph=DraftTutorialGraph(
                graph_id=graph.graph_id,
                title=graph.title,
                recorded_app=graph.recorded_app,
                start_node_id=graph.start_node_id,
                nodes=graph.nodes,
                transitions=graph.transitions,
            )
        )
