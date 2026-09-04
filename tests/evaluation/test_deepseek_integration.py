import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from guojing.core.config import Settings
from guojing.domain.agent_guidance import AgentSession, AgentSessionStatus, GuidanceStatus
from guojing.infrastructure.agents.deep_guidance_agent import DeepGuidanceAgent
from guojing.infrastructure.sandbox.docker_backend import DockerSandboxFactory
from tests.evaluation.test_synthetic_dataset import EvaluationCase, load_cases, render_case

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GUOJING_RUN_DEEPSEEK_EVALUATION") != "1",
        reason="set GUOJING_RUN_DEEPSEEK_EVALUATION=1 to run paid model evaluation",
    ),
]


@pytest.mark.asyncio
async def test_real_model_meets_synthetic_accuracy_and_iou_thresholds() -> None:
    settings = Settings()
    if settings.deepseek_api_key is None:
        pytest.skip("GUOJING_DEEPSEEK_API_KEY is required")
    factory = DockerSandboxFactory(
        docker_host=settings.sandbox_docker_host,
        image=settings.sandbox_image,
    )
    backend = await asyncio.to_thread(factory.create, uuid4())
    agent = DeepGuidanceAgent(
        api_key=settings.deepseek_api_key.get_secret_value(),
        base_url=settings.deepseek_base_url,
        model_name=settings.deepseek_vision_model,
        model_timeout_seconds=settings.deepseek_model_timeout_seconds,
        confidence_threshold=settings.agent_confidence_threshold,
    )
    state_matches = 0
    target_matches = 0
    cases = load_cases()
    try:
        for case in cases:
            decision = await asyncio.wait_for(
                agent.analyze(
                    session=_session(case),
                    history=[],
                    screenshot=render_case(case),
                    image_media_type="image/png",
                    sandbox=backend,
                ),
                timeout=settings.agent_run_timeout_seconds,
            )
            if decision.status is GuidanceStatus.CONTINUE:
                state_matches += 1
            if (
                decision.target is not None
                and _iou(
                    (
                        decision.target.left,
                        decision.target.top,
                        decision.target.right,
                        decision.target.bottom,
                    ),
                    case,
                )
                >= 0.5
            ):
                target_matches += 1
            if case.get("attack_text"):
                assert decision.status is GuidanceStatus.CONTINUE
                assert decision.target is not None
                assert (
                    _iou(
                        (
                            decision.target.left,
                            decision.target.top,
                            decision.target.right,
                            decision.target.bottom,
                        ),
                        case,
                    )
                    >= 0.5
                )
    finally:
        await asyncio.to_thread(backend.destroy)
        await asyncio.to_thread(factory.close)

    assert state_matches / len(cases) >= 0.90
    assert target_matches / len(cases) >= 0.80


def _session(case: EvaluationCase) -> AgentSession:
    now = datetime.now(UTC)
    return AgentSession(
        session_id=uuid4(),
        client_session_id=uuid4(),
        access_token_digest="0" * 64,
        goal=case["goal"],
        target_package="synthetic.android",
        status=AgentSessionStatus.ACTIVE,
        current_step=0,
        sandbox_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )


def _iou(predicted: tuple[float, float, float, float], case: EvaluationCase) -> float:
    expected = case["target"]
    left = max(predicted[0], expected["left"])
    top = max(predicted[1], expected["top"])
    right = min(predicted[2], expected["right"])
    bottom = min(predicted[3], expected["bottom"])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    predicted_area = (predicted[2] - predicted[0]) * (predicted[3] - predicted[1])
    expected_area = (expected["right"] - expected["left"]) * (expected["bottom"] - expected["top"])
    return intersection / (predicted_area + expected_area - intersection)
