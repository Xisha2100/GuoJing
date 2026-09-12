"""Default Chinese guidance; only the user's goal may enable English terms."""

import unicodedata

from guojing.domain.agent_guidance import GuidanceDecision, GuidanceStatus


def allows_english(goal: str) -> bool:
    """Recognize Latin letters, including full-width input, without inspecting the screenshot."""
    return any("LATIN" in unicodedata.name(char, "") for char in goal if char.isalpha())


def enforce_guidance_language(goal: str, decision: GuidanceDecision) -> GuidanceDecision:
    """Suppress an English-bearing step when the user requested a Chinese-only session."""
    if not allows_english(goal) and allows_english(decision.instruction or ""):
        return GuidanceDecision(
            status=GuidanceStatus.CANNOT_DETERMINE,
            instruction="本次指引未能生成中文说明,请重新识别。",
            target=None,
            confidence=decision.confidence,
        )
    return decision
