"""Run real installed Deep Agents graphs with a scripted, network-free provider."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from deepagents.backends.filesystem import FilesystemBackend
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from langsmith import get_tracing_context

from guojing.application.agent.ports import SandboxHandle
from guojing.application.agent.usage import ModelUsage, current_usage
from guojing.core.config import GuidanceEngine
from guojing.domain.agent_guidance import AgentSession, AgentSessionStatus, GuidanceStatus
from guojing.infrastructure.agents.deep_guidance_agent import DeepGuidanceAgent

CANDIDATE: dict[str, Any] = {
    "status": "continue",
    "instruction": "点击设置按钮",
    "target": {"left": 0.1, "top": 0.2, "right": 0.3, "bottom": 0.4},
    "confidence": 0.95,
    "target_description": "左侧设置按钮",
    "evidence": "当前页面可见唯一设置按钮",
    "risk": "ordinary",
}
ANALYSIS = {
    "current_page": "首页",
    "visible_controls": [],
    "likely_target": CANDIDATE["target"],
    "summary": "当前页面可见唯一设置按钮",
}


def session(goal: str = "打开设置") -> AgentSession:
    now = datetime.now(UTC)
    return AgentSession(
        session_id=uuid4(),
        client_session_id=uuid4(),
        access_token_digest="a" * 64,
        goal=goal,
        target_package="com.example.app",
        status=AgentSessionStatus.ACTIVE,
        current_step=0,
        sandbox_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )


def agent(engine: GuidanceEngine = GuidanceEngine.BOUNDED) -> DeepGuidanceAgent:
    return DeepGuidanceAgent(
        api_key="offline-test",
        base_url="https://example.invalid/v1",
        model_name="offline-vision",
        model_timeout_seconds=1,
        confidence_threshold=0.7,
        engine=engine,
    )


class Script:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.candidate = dict(CANDIDATE)
        self.revised_candidate: dict[str, Any] | None = None
        self.reviews: list[dict[str, Any]] = []
        self.calls: list[str] = []
        self.tools: list[set[str]] = []
        self.images: list[bool] = []
        self.review_inputs: list[dict[str, Any]] = []
        self.main_turn = 0
        self.fault: tuple[str, str] | None = None
        self.change_final = False
        self.repeat_task_id = False
        self.task_arguments: dict[str, Any] | None = None
        self.output_mode = "single"

        async def generate(_model: ChatOpenAI, messages: list[Any], **kwargs: Any) -> ChatResult:
            assert get_tracing_context()["enabled"] is False
            names = {tool["function"]["name"] for tool in kwargs["tools"]}
            self.tools.append(names)
            self.images.append(
                any(
                    isinstance(message.content, list)
                    and any(block.get("type") == "image_url" for block in message.content)
                    for message in messages
                )
            )
            args: dict[str, Any]
            if "GuidanceCandidateOutput" in names:
                name = "GuidanceCandidateOutput"
                args = (
                    self.revised_candidate
                    if self.calls.count(name) and self.revised_candidate
                    else self.candidate
                )
            elif "UiAnalysisOutput" in names:
                name, args = "UiAnalysisOutput", ANALYSIS
            elif "GuidanceReviewOutput" in names:
                name = "GuidanceReviewOutput"
                inputs = []
                for message in messages:
                    if message.type != "human":
                        continue
                    content = message.content
                    text = content if isinstance(content, str) else content[0]["text"]
                    inputs.append(json.loads(text))
                data = next(value for value in reversed(inputs) if "candidate_digest" in value)
                self.review_inputs.append(data)
                args = {
                    "candidate_digest": data["candidate_digest"],
                    "approved": True,
                    "issue": "none",
                    "risk": "ordinary",
                    "target_supported": True,
                    "completion_supported": True,
                    "feedback": "可用",
                }
                if self.reviews:
                    args.update(self.reviews.pop(0))
            else:
                assert "GuidanceDecisionOutput" in names
                self.main_turn += 1
                if self.main_turn <= 2:
                    name = "task"
                    args = {
                        "subagent_type": "ui-analyst"
                        if self.main_turn == 1
                        else "guidance-reviewer",
                        "description": "分析当前截图"
                        if self.main_turn == 1
                        else json.dumps(self.candidate, ensure_ascii=False),
                    }
                else:
                    name = "GuidanceDecisionOutput"
                    args = {
                        key: self.candidate[key]
                        for key in ("status", "instruction", "target", "confidence")
                    }
                    if self.change_final:
                        args["instruction"] = "点击其他按钮"
            self.calls.append(name)
            call_id = "repeated" if self.repeat_task_id and name == "task" else str(uuid4())
            if self.fault and self.fault[0] == name:
                name = self.fault[1]
                args = {"command": "false", "file_path": "/workspace/secret", "content": "changed"}
            if name == "task" and self.task_arguments is not None:
                args = self.task_arguments
            calls = [{"name": name, "args": args, "id": call_id}]
            if self.output_mode == "none":
                calls = []
            elif self.output_mode == "multiple":
                calls *= 2
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=calls,
                        )
                    )
                ]
            )

        monkeypatch.setattr(ChatOpenAI, "_agenerate", generate)


async def run_agent(
    engine: GuidanceEngine, tmp_path: Path, goal: str = "打开设置"
) -> tuple[Any, ModelUsage]:
    usage = ModelUsage(lambda: None)
    token = current_usage.set(usage)
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=True)
    try:
        result = await agent(engine).analyze(
            session=session(goal),
            history=[],
            screenshot=b"offline-image",
            image_media_type="image/png",
            sandbox=cast(SandboxHandle, backend)
            if engine is GuidanceEngine.LEGACY_HARDENED
            else None,
        )
    finally:
        current_usage.reset(token)
    return result, usage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "engine,expected", [(GuidanceEngine.BOUNDED, 2), (GuidanceEngine.LEGACY_HARDENED, 5)]
)
async def test_installed_graph_has_only_allowed_tools_and_counts_every_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    engine: GuidanceEngine,
    expected: int,
) -> None:
    script = Script(monkeypatch)
    decision, usage = await run_agent(engine, tmp_path)
    assert decision.status is GuidanceStatus.CONTINUE
    assert decision.instruction == CANDIDATE["instruction"]
    assert usage.calls == expected
    assert sum(int(item["model_calls"]) for item in usage.stages) == expected
    assert usage.engine == engine.value
    forbidden = {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"}
    assert all(not tools & forbidden for tools in script.tools)
    if engine is GuidanceEngine.BOUNDED:
        assert script.calls == ["GuidanceCandidateOutput", "GuidanceReviewOutput"]
        assert script.images == [True, True]
        assert not list(tmp_path.iterdir())
        assert [item["model_calls"] for item in usage.stages] == [1, 1]
    else:
        assert script.calls == [
            "task",
            "UiAnalysisOutput",
            "task",
            "GuidanceReviewOutput",
            "GuidanceDecisionOutput",
        ]
        assert script.images == [True, True, True, False, True]
        assert "task" not in script.tools[1] and "task" not in script.tools[3]
    assert script.review_inputs[0]["candidate"] == script.candidate


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["GuidanceCandidateOutput", "GuidanceReviewOutput"])
@pytest.mark.parametrize("tool", ["execute", "read_file", "write_file", "task", "future_tool"])
async def test_unadvertised_tools_are_rejected_without_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stage: str,
    tool: str,
) -> None:
    script = Script(monkeypatch)
    script.fault = (stage, tool)
    decision, usage = await run_agent(GuidanceEngine.BOUNDED, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE
    assert usage.calls <= 2
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_one_wording_revision_is_reviewed_and_shares_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = Script(monkeypatch)
    script.reviews = [{"approved": False, "issue": "wording", "feedback": "补充左侧位置"}]
    script.revised_candidate = {**CANDIDATE, "instruction": "点击左侧设置按钮"}
    decision, usage = await run_agent(GuidanceEngine.BOUNDED, tmp_path)
    assert decision.instruction == "点击左侧设置按钮"
    assert usage.calls == 4
    assert (
        script.review_inputs[0]["candidate_digest"] != script.review_inputs[1]["candidate_digest"]
    )
    assert all(script.images)


@pytest.mark.asyncio
async def test_revision_rejected_again_stops_after_four_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script = Script(monkeypatch)
    script.reviews = [{"approved": False, "issue": "wording"}] * 2
    decision, usage = await run_agent(GuidanceEngine.BOUNDED, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE
    assert usage.calls == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "review",
    [
        {"approved": False, "issue": "visual"},
        {"candidate_digest": "0" * 64},
        {"risk": "unknown"},
        {"target_supported": False},
    ],
)
@pytest.mark.parametrize("engine", list(GuidanceEngine))
async def test_unsafe_or_mismatched_reviews_never_reach_display(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    review: dict[str, Any],
    engine: GuidanceEngine,
) -> None:
    script = Script(monkeypatch)
    script.reviews = [review]
    decision, _ = await run_agent(engine, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE
    assert decision.target is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["change_final", "repeat_task_id"])
async def test_legacy_cannot_rewrite_approved_candidate_or_repeat_delegation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    script = Script(monkeypatch)
    setattr(script, fault, True)
    decision, _ = await run_agent(GuidanceEngine.LEGACY_HARDENED, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "goal,instruction,status",
    [
        ("打开设置", "Click Settings", GuidanceStatus.CANNOT_DETERMINE),
        ("搜索 OpenAI", "在搜索框输入 OpenAI", GuidanceStatus.CONTINUE),
    ],
)
async def test_language_policy_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    goal: str,
    instruction: str,
    status: GuidanceStatus,
) -> None:
    script = Script(monkeypatch)
    script.candidate["instruction"] = instruction
    decision, _ = await run_agent(GuidanceEngine.BOUNDED, tmp_path, goal)
    assert decision.status is status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate",
    [
        {"confidence": 0.3},
        {"risk": "financial"},
        {"evidence": ""},
        {"instruction": "点击确认删除按钮"},
        {"confidence": float("nan")},
        {"confidence": "0.99"},
        {"status": "future"},
        {"target": {"left": 0.5, "top": 0.2, "right": 0.3, "bottom": 0.4}},
    ],
)
async def test_invalid_candidates_fail_closed_without_hidden_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    candidate: dict[str, Any],
) -> None:
    script = Script(monkeypatch)
    script.candidate.update(candidate)
    decision, usage = await run_agent(GuidanceEngine.BOUNDED, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE
    assert usage.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("supported", [True, False])
async def test_completion_requires_current_visual_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    supported: bool,
) -> None:
    script = Script(monkeypatch)
    script.candidate.update(status="completed", target=None, instruction="设置页面已打开")
    script.reviews = [{"completion_supported": supported}]
    decision, _ = await run_agent(GuidanceEngine.BOUNDED, tmp_path)
    assert decision.status is (
        GuidanceStatus.COMPLETED if supported else GuidanceStatus.CANNOT_DETERMINE
    )
    assert decision.target is None


@pytest.mark.asyncio
async def test_cancellation_propagates_without_review(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def generate(_model: ChatOpenAI, *args: Any, **kwargs: Any) -> ChatResult:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        raise AssertionError("unreachable")

    monkeypatch.setattr(ChatOpenAI, "_agenerate", generate)
    task = asyncio.create_task(
        agent().analyze(
            session=session(),
            history=[],
            screenshot=b"image",
            image_media_type="image/png",
        )
    )
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["none", "multiple"])
async def test_missing_or_multiple_outputs_stop_after_one_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    script = Script(monkeypatch)
    script.output_mode = mode
    decision, usage = await run_agent(GuidanceEngine.BOUNDED, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE
    assert usage.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["approved", "target_supported"])
async def test_review_booleans_are_not_coerced_from_strings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str
) -> None:
    script = Script(monkeypatch)
    script.reviews = [{field: "true"}]
    decision, usage = await run_agent(GuidanceEngine.BOUNDED, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE
    assert usage.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {"subagent_type": "ui-analyst"},
        {"subagent_type": "ui-analyst", "description": 123},
        {"subagent_type": "ui-analyst", "description": ""},
        {"subagent_type": "general-purpose", "description": "分析"},
        {"subagent_type": "guidance-reviewer", "description": "提前审校"},
        {"subagent_type": "ui-analyst", "description": "分析", "extra": "forbidden"},
    ],
)
async def test_invalid_legacy_delegation_is_rejected_before_any_subagent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, arguments: dict[str, Any]
) -> None:
    script = Script(monkeypatch)
    script.task_arguments = arguments
    decision, usage = await run_agent(GuidanceEngine.LEGACY_HARDENED, tmp_path)
    assert decision.status is GuidanceStatus.CANNOT_DETERMINE
    assert usage.calls == 1
    assert script.calls == ["task"]


@pytest.mark.asyncio
async def test_concurrent_runs_keep_images_candidates_and_budgets_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import base64

    seen: dict[str, list[str]] = {}

    async def generate(_model: ChatOpenAI, messages: list[Any], **kwargs: Any) -> ChatResult:
        assert get_tracing_context()["enabled"] is False
        content = next(message.content for message in reversed(messages) if message.type == "human")
        data = json.loads(content[0]["text"])
        goal = data["goal"]
        image = content[1]["image_url"]["url"]
        assert base64.b64decode(image.split(",")[1]).decode() == goal
        seen.setdefault(goal, []).append(image)
        name = kwargs["tools"][0]["function"]["name"]
        await asyncio.sleep(0)
        if name == "GuidanceCandidateOutput":
            arguments = {**CANDIDATE, "instruction": goal}
        else:
            assert data["candidate"]["instruction"] == goal
            arguments = {
                "candidate_digest": data["candidate_digest"],
                "approved": True,
                "issue": "none",
                "risk": "ordinary",
                "target_supported": True,
                "completion_supported": True,
                "feedback": "可用",
            }
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[{"name": name, "args": arguments, "id": str(uuid4())}],
                    )
                )
            ]
        )

    monkeypatch.setattr(ChatOpenAI, "_agenerate", generate)
    shared_agent = agent()

    async def run(goal: str) -> None:
        usage = ModelUsage(lambda: None)
        token = current_usage.set(usage)
        try:
            decision = await shared_agent.analyze(
                session=session(goal),
                history=[],
                screenshot=goal.encode(),
                image_media_type="image/png",
            )
            assert decision.status is GuidanceStatus.CONTINUE
            assert decision.instruction == goal
            assert usage.calls == 2
        finally:
            current_usage.reset(token)

    await asyncio.gather(run("点击设置按钮"), run("点击搜索按钮"))
    assert all(len(images) == 2 and images[0] == images[1] for images in seen.values())
