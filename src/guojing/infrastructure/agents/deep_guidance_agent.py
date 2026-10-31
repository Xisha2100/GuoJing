"""Two selectable, bounded Deep Agents implementations of the same application port."""

import asyncio
import base64
import json
from collections.abc import Sequence
from typing import cast

from deepagents import create_deep_agent
from deepagents.backends.protocol import SandboxBackendProtocol
from deepagents.middleware.subagents import SubAgent
from langchain.agents.structured_output import StructuredOutputError, ToolStrategy
from langchain_openai import ChatOpenAI
from langsmith import tracing_context
from pydantic import ValidationError

from guojing.application.agent.context import run_context
from guojing.application.agent.ports import SandboxHandle
from guojing.application.agent.usage import ModelUsage, current_usage
from guojing.core.config import GuidanceEngine
from guojing.domain.agent_guidance import AgentSession, GuidanceDecision, GuidanceStep
from guojing.domain.guidance_policy import accept_reviewed_candidate, cannot_determine
from guojing.infrastructure.agents.harness import (
    GuidanceRejected,
    GuidanceToolGuard,
    file_middleware,
    file_permissions,
    register_guidance_profile,
)
from guojing.infrastructure.agents.outputs import (
    GuidanceCandidateOutput,
    GuidanceDecisionOutput,
    GuidanceReviewOutput,
    UiAnalysisOutput,
)
from guojing.infrastructure.agents.prompts import (
    GUIDANCE_REVIEWER_PROMPT,
    MAIN_PROMPT,
    UI_ANALYST_PROMPT,
    language_prompt,
)
from guojing.infrastructure.agents.usage_callback import UsageCallback
from guojing.infrastructure.agents.validation import FixedDelegationGuard, require_fixed_subagents
from guojing.infrastructure.agents.workflow import PROMPT_VERSION, bounded_guidance, image_message


class DeepGuidanceAgent:
    """Keep the hardened legacy graph available until visual evaluation permits rollout."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        model_timeout_seconds: int,
        confidence_threshold: float,
        engine: GuidanceEngine = GuidanceEngine.LEGACY_HARDENED,
    ) -> None:
        register_guidance_profile(model_name)
        self._engine = GuidanceEngine(engine)
        self._confidence_threshold = confidence_threshold
        self._model = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            timeout=model_timeout_seconds,
            max_retries=0,
            max_tokens=2048,
            use_responses_api=False,
            temperature=0,
            # DeepSeek thinking mode rejects the specific tool selected by ToolStrategy.
            extra_body={"thinking": {"type": "disabled"}},
        )

    async def analyze(
        self,
        *,
        session: AgentSession,
        history: Sequence[GuidanceStep],
        screenshot: bytes,
        image_media_type: str,
        sandbox: SandboxHandle | None = None,
    ) -> GuidanceDecision:
        if image_media_type not in {"image/jpeg", "image/png"}:
            raise ValueError("unsupported screenshot media type")
        usage = current_usage.get() or ModelUsage(lambda: None)
        usage.engine = self._engine.value
        usage.prompt_version = (
            PROMPT_VERSION if self._engine is GuidanceEngine.BOUNDED else "legacy-2"
        )
        image_url = f"data:{image_media_type};base64,{base64.b64encode(screenshot).decode('ascii')}"
        # Includes all nodes, repairs and exceptions; global tracing cannot opt a run in.
        with tracing_context(enabled=False):
            try:
                if self._engine is GuidanceEngine.BOUNDED:
                    return await bounded_guidance(
                        self._model,
                        session=session,
                        history=history,
                        image_url=image_url,
                        threshold=self._confidence_threshold,
                        usage=usage,
                    )
                if sandbox is None:
                    raise RuntimeError("legacy guidance requires a sandbox")
                return await self._legacy(
                    session=session,
                    history=history,
                    image_url=image_url,
                    screenshot=screenshot,
                    image_media_type=image_media_type,
                    backend=cast(SandboxBackendProtocol, sandbox),
                    usage=usage,
                )
            except (GuidanceRejected, ValidationError, StructuredOutputError):
                # Model refusal/invalid output is a normal inability to guide. Transport,
                # cancellation and the shared call budget remain run-level failures.
                usage.rejection = "invalid_model_output"
                return cannot_determine()

    async def _legacy(
        self,
        *,
        session: AgentSession,
        history: Sequence[GuidanceStep],
        image_url: str,
        screenshot: bytes,
        image_media_type: str,
        backend: SandboxBackendProtocol,
        usage: ModelUsage,
    ) -> GuidanceDecision:
        suffix = "jpg" if image_media_type == "image/jpeg" else "png"
        screenshot_path = f"/workspace/current-screen.{suffix}"
        upload = await asyncio.to_thread(backend.upload_files, [(screenshot_path, screenshot)])
        if len(upload) != 1 or upload[0].error is not None or upload[0].path != screenshot_path:
            raise RuntimeError("sandbox screenshot upload failed")
        guard = FixedDelegationGuard(session.goal, usage)
        agent = create_deep_agent(
            model=self._model,
            system_prompt=(
                MAIN_PROMPT
                + "\n"
                + language_prompt(session.goal)
                + "\nGuidanceCandidateOutput JSON schema:\n"
                + json.dumps(GuidanceCandidateOutput.model_json_schema(), ensure_ascii=False)
            ),
            subagents=self._subagents(session.goal, backend, usage),
            backend=backend,
            permissions=file_permissions(),
            middleware=[file_middleware(backend), guard],
            response_format=ToolStrategy(GuidanceDecisionOutput, handle_errors=False),
        )
        result = await agent.ainvoke(
            {"messages": [image_message(run_context(session, history), image_url)]},
            config={"recursion_limit": 16, "callbacks": [UsageCallback(usage)]},
        )
        require_fixed_subagents(result)
        output = GuidanceDecisionOutput.model_validate(result.get("structured_response"))
        guard.require_unchanged_candidate(output)
        if guard.candidate is None or guard.review is None:
            raise GuidanceRejected("missing_review")
        decision = accept_reviewed_candidate(
            session.goal,
            guard.candidate.candidate(),
            guard.review.to_domain(),
            threshold=self._confidence_threshold,
        )
        if decision != guard.candidate.to_domain():
            usage.rejection = "review_policy"
        return decision

    def _subagents(
        self, goal: str, backend: SandboxBackendProtocol, usage: ModelUsage
    ) -> list[SubAgent]:
        return [
            {
                "name": "ui-analyst",
                "description": "Inspect the inherited screenshot and report visible UI targets.",
                "system_prompt": UI_ANALYST_PROMPT + "\n" + language_prompt(goal),
                "model": self._model,
                "tools": [],
                "middleware": [
                    file_middleware(backend),
                    GuidanceToolGuard("UiAnalysisOutput", usage=usage, stage="analysis"),
                ],
                "response_format": ToolStrategy(UiAnalysisOutput, handle_errors=False),
                "mode": "fork",
            },
            {
                "name": "guidance-reviewer",
                "description": "Review a frozen JSON candidate against the host-supplied analysis.",
                "system_prompt": GUIDANCE_REVIEWER_PROMPT + "\n" + language_prompt(goal),
                "model": self._model,
                "tools": [],
                "middleware": [
                    file_middleware(backend),
                    GuidanceToolGuard("GuidanceReviewOutput", usage=usage, stage="text_review"),
                ],
                "response_format": ToolStrategy(GuidanceReviewOutput, handle_errors=False),
                "mode": "isolated",
            },
        ]
