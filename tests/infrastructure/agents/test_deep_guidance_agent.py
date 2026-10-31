from typing import Any, cast

import pytest
from deepagents.backends.protocol import FileUploadResponse
from tests.infrastructure.agents.test_deepagents_compatibility import agent

from guojing.core.config import GuidanceEngine
from guojing.domain.agent_guidance import AgentSession
from guojing.infrastructure.agents.outputs import GuidanceDecisionOutput, TargetOutput


def test_model_instruction_limit_preserves_complete_text() -> None:
    target = TargetOutput(left=0.1, top=0.1, right=0.2, bottom=0.2)
    accepted = GuidanceDecisionOutput(
        status="continue", instruction="点" * 80, target=target, confidence=0.9
    )
    assert accepted.instruction == "点" * 80
    with pytest.raises(ValueError):
        GuidanceDecisionOutput(
            status="continue", instruction="点" * 81, target=target, confidence=0.9
        )


def test_model_settings_disable_transport_retries_and_thinking() -> None:
    model = agent()._model
    assert model.max_retries == 0
    assert model.use_responses_api is False
    assert model.extra_body == {"thinking": {"type": "disabled"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["empty", "error", "wrong_path", "duplicate", "media_type"])
async def test_invalid_upload_never_starts_model(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class FailedSandbox:
        id = "failed-upload"

        def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
            assert failure != "media_type"
            path = files[0][0]
            if failure == "empty":
                return []
            if failure == "error":
                return [FileUploadResponse(path=path, error="upload_failed")]
            if failure == "wrong_path":
                return [FileUploadResponse(path="/wrong.jpg", error=None)]
            return [FileUploadResponse(path=path, error=None)] * 2

    def unexpected_graph(**kwargs: Any) -> None:
        pytest.fail("must validate upload before building the agent graph")

    monkeypatch.setattr(
        "guojing.infrastructure.agents.deep_guidance_agent.create_deep_agent", unexpected_graph
    )
    with pytest.raises((ValueError, RuntimeError)):
        await agent(GuidanceEngine.LEGACY_HARDENED).analyze(
            session=cast(AgentSession, None),
            history=[],
            screenshot=b"image-bytes",
            image_media_type="image/gif" if failure == "media_type" else "image/jpeg",
            sandbox=FailedSandbox(),
        )
