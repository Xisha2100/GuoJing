from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from guojing.application.help_requests.deep_agent_adapter import DeepAgentGuidanceModel
from guojing.application.help_requests.model_adapter import ModelGuidanceContext
from guojing.domain.help_requests import HelpRequestIntent, HelpRequestProcessingRoute


def test_deep_agent_adapter_exposes_only_safe_context() -> None:
    received: dict[str, object] = {}

    class Invoker:
        def invoke(self, payload: Mapping[str, object]) -> Mapping[str, object]:
            received.update(payload)
            return {"action_ids": ["general.observe_page"]}

    context = ModelGuidanceContext(
        request_id=uuid4(),
        intent=HelpRequestIntent.GENERAL_GUIDANCE,
        processing_route=HelpRequestProcessingRoute.GENERAL_GUIDANCE,
        task="safe task",
        safety_rules=("manual only",),
        deadline_at=datetime.now(UTC),
    )

    result = DeepAgentGuidanceModel(Invoker()).generate(context, deadline=datetime.now(UTC))

    assert result == {"action_ids": ["general.observe_page"]}
    assert set(received) == {"task", "safety_rules", "output_schema"}
