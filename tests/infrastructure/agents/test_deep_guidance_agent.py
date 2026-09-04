from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from deepagents.backends.protocol import FileUploadResponse, SandboxBackendProtocol
from langchain_core.messages import AIMessage

from guojing.domain.agent_guidance import AgentSession, AgentSessionStatus, GuidanceStatus
from guojing.infrastructure.agents import deep_guidance_agent as module
from guojing.infrastructure.agents.deep_guidance_agent import (
    DeepGuidanceAgent,
    GuidanceDecisionOutput,
    TargetOutput,
)


class FakeSandbox:
    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        assert files[0][0] == "/workspace/current-screen.jpg"
        assert files[0][1] == b"image-bytes"
        return [FileUploadResponse(path=files[0][0], error=None)]


@pytest.mark.asyncio
async def test_real_deepagents_composition_receives_image_and_fixed_subagents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class CompiledAgent:
        async def ainvoke(
            self,
            payload: Mapping[str, object],
            config: Mapping[str, object],
        ) -> dict[str, object]:
            captured["payload"] = payload
            captured["config"] = config
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {"subagent_type": "ui-analyst"},
                                "id": "one",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {"subagent_type": "guidance-reviewer"},
                                "id": "two",
                                "type": "tool_call",
                            },
                        ],
                    ),
                ],
                "structured_response": GuidanceDecisionOutput(
                    status="continue",
                    instruction="点击右上角的加号",
                    target=TargetOutput(left=0.8, top=0.1, right=0.9, bottom=0.2),
                    confidence=0.95,
                ),
            }

    def fake_create_deep_agent(**kwargs: object) -> CompiledAgent:
        captured["composition"] = kwargs
        return CompiledAgent()

    monkeypatch.setattr(module, "create_deep_agent", fake_create_deep_agent)
    now = datetime.now(UTC)
    session = AgentSession(
        session_id=uuid4(),
        client_session_id=uuid4(),
        access_token_digest="a" * 64,
        goal="打开扫一扫",
        target_package="com.tencent.mm",
        status=AgentSessionStatus.ACTIVE,
        current_step=0,
        sandbox_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )
    agent = DeepGuidanceAgent(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model_name="deepseek-v4-flash-vision-exp",
        model_timeout_seconds=30,
        confidence_threshold=0.7,
    )
    assert agent._model.model_name == "deepseek-v4-flash-vision-exp"
    assert agent._model.openai_api_base == "https://api.deepseek.com"
    assert agent._model.request_timeout == 30
    assert agent._model.max_retries == 0
    assert agent._model.use_responses_api is False

    result = await agent.analyze(
        session=session,
        history=[],
        screenshot=b"image-bytes",
        image_media_type="image/jpeg",
        sandbox=cast(SandboxBackendProtocol, FakeSandbox()),
    )

    assert result.status is GuidanceStatus.CONTINUE
    composition = cast(dict[str, Any], captured["composition"])
    assert [item["name"] for item in composition["subagents"]] == [
        "ui-analyst",
        "guidance-reviewer",
    ]
    assert [item["mode"] for item in composition["subagents"]] == ["fork", "isolated"]
    assert "response_format" in composition
    assert all("response_format" in item for item in composition["subagents"])
    assert "checkpointer" not in composition
    payload = cast(dict[str, Any], captured["payload"])
    image_block = payload["messages"][0]["content"][1]
    assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_low_confidence_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class CompiledAgent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            calls = [
                {
                    "name": "task",
                    "args": {"subagent_type": name},
                    "id": name,
                    "type": "tool_call",
                }
                for name in ("ui-analyst", "guidance-reviewer")
            ]
            return {
                "messages": [
                    AIMessage(content="", tool_calls=[calls[0]]),
                    AIMessage(content="", tool_calls=[calls[1]]),
                ],
                "structured_response": {
                    "status": "continue",
                    "instruction": "点击按钮",
                    "target": {"left": 0.1, "top": 0.1, "right": 0.2, "bottom": 0.2},
                    "confidence": 0.3,
                },
            }

    monkeypatch.setattr(module, "create_deep_agent", lambda **_kwargs: CompiledAgent())
    now = datetime.now(UTC)
    session = AgentSession(
        session_id=uuid4(),
        client_session_id=uuid4(),
        access_token_digest="a" * 64,
        goal="打开扫一扫",
        target_package="com.tencent.mm",
        status=AgentSessionStatus.ACTIVE,
        current_step=0,
        sandbox_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )
    agent = DeepGuidanceAgent(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model_name="deepseek-v4-flash-vision-exp",
        model_timeout_seconds=30,
        confidence_threshold=0.7,
    )

    result = await agent.analyze(
        session=session,
        history=[],
        screenshot=b"image-bytes",
        image_media_type="image/jpeg",
        sandbox=cast(SandboxBackendProtocol, FakeSandbox()),
    )

    assert result.status is GuidanceStatus.CANNOT_DETERMINE
    assert result.target is None
