"""A bounded two-stage workflow; only the reviewed candidate reaches the domain."""

import json
from collections.abc import Sequence
from time import monotonic
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from guojing.application.agent.context import run_context
from guojing.application.agent.usage import ModelUsage
from guojing.domain.agent_guidance import AgentSession, GuidanceDecision, GuidanceStep
from guojing.domain.guidance_policy import (
    accept_reviewed_candidate,
    can_revise,
    candidate_is_safe,
    cannot_determine,
)
from guojing.infrastructure.agents.harness import (
    GuidanceToolGuard,
    file_middleware,
    file_permissions,
)
from guojing.infrastructure.agents.outputs import GuidanceCandidateOutput, GuidanceReviewOutput
from guojing.infrastructure.agents.prompts import (
    CANDIDATE_PROMPT,
    VISUAL_REVIEW_PROMPT,
    language_prompt,
)
from guojing.infrastructure.agents.usage_callback import UsageCallback

PROMPT_VERSION = "bounded-1"


def image_message(context: str, image_url: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": context},
            {"type": "image_url", "image_url": {"url": image_url}},
        ],
    }


async def invoke_stage[OutputT: BaseModel](
    model: BaseChatModel,
    schema: type[OutputT],
    *,
    prompt: str,
    context: str,
    image_url: str,
    stage: str,
    usage: ModelUsage,
) -> OutputT:
    backend = StateBackend()
    graph = create_deep_agent(
        model=model,
        system_prompt=prompt,
        subagents=[],
        backend=backend,
        permissions=file_permissions(),
        middleware=[file_middleware(backend), GuidanceToolGuard(schema.__name__)],
        response_format=ToolStrategy(schema, handle_errors=False),
    )
    started = monotonic()
    calls, input_tokens, output_tokens = usage.calls, usage.input_tokens, usage.output_tokens
    try:
        result = await graph.ainvoke(
            {"messages": [image_message(context, image_url)]},
            config={"recursion_limit": 4, "callbacks": [UsageCallback(usage)]},
        )
        return schema.model_validate(result.get("structured_response"))
    finally:
        usage.stages.append(
            {
                "stage": stage,
                "model_calls": usage.calls - calls,
                "input_tokens": usage.input_tokens - input_tokens,
                "output_tokens": usage.output_tokens - output_tokens,
                "duration_ms": round((monotonic() - started) * 1000),
            }
        )


async def bounded_guidance(
    model: ChatOpenAI,
    *,
    session: AgentSession,
    history: Sequence[GuidanceStep],
    image_url: str,
    threshold: float,
    usage: ModelUsage,
) -> GuidanceDecision:
    context = run_context(session, history)
    language = "\n" + language_prompt(session.goal)
    for attempt in range(2):
        output = await invoke_stage(
            model,
            GuidanceCandidateOutput,
            prompt=CANDIDATE_PROMPT + language,
            context=context,
            image_url=image_url,
            stage="candidate" if attempt == 0 else "revision",
            usage=usage,
        )
        candidate = output.candidate()
        if not candidate_is_safe(candidate, threshold=threshold):
            usage.rejection = "candidate_policy"
            return cannot_determine()
        review = await invoke_stage(
            model,
            GuidanceReviewOutput,
            prompt=VISUAL_REVIEW_PROMPT + language,
            context=json.dumps(
                {
                    "goal": session.goal,
                    "candidate": output.model_dump(),
                    "candidate_digest": candidate.digest,
                },
                ensure_ascii=False,
            ),
            image_url=image_url,
            stage="review" if attempt == 0 else "revision_review",
            usage=usage,
        )
        verdict = review.to_domain()
        if attempt == 0 and can_revise(candidate, verdict, threshold=threshold):
            usage.revisions += 1
            context = json.dumps(
                {
                    "request": json.loads(run_context(session, history)),
                    "previous_candidate": output.model_dump(),
                    "wording_feedback": review.feedback,
                },
                ensure_ascii=False,
            )
            continue
        decision = accept_reviewed_candidate(session.goal, candidate, verdict, threshold=threshold)
        if decision != candidate.decision:
            usage.rejection = "review_policy"
        return decision
    return cannot_determine()
