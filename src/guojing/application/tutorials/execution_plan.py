"""Resolve a pinned, risk-bounded execution plan from a tutorial match."""

from guojing.application.tutorials.matcher import TutorialMatchCandidate
from guojing.application.tutorials.service import TutorialService
from guojing.domain.guidance_actions import GuidanceAuthorization, authorize_guidance_action
from guojing.domain.help_requests import HelpRequestTutorialPlan


class TutorialExecutionPlanService:
    """Pin one published revision and expose only low-risk outgoing transitions."""

    def __init__(self, tutorial_service: TutorialService) -> None:
        self._tutorial_service = tutorial_service

    def build(self, candidate: TutorialMatchCandidate) -> HelpRequestTutorialPlan:
        published = self._tutorial_service.get_published(candidate.graph_id)
        if published.revision_number != candidate.revision_number:
            raise ValueError("matched tutorial revision is no longer published")
        transitions = tuple(
            transition
            for transition in published.graph.transitions
            if transition.source_node_id == candidate.node_id
            and authorize_guidance_action(transition.risk_level) is GuidanceAuthorization.ALLOW
        )
        return HelpRequestTutorialPlan(
            graph_id=candidate.graph_id,
            node_id=candidate.node_id,
            revision_number=candidate.revision_number,
            compatibility_status=candidate.reuse_assessment.status.value,
            allowed_transition_ids=tuple(transition.transition_id for transition in transitions),
        )
