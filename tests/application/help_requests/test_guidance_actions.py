"""Approved-action catalog tests for automated help guidance."""

import pytest

from guojing.application.help_requests.guidance_actions import (
    GuidanceActionCatalog,
    UnknownGuidanceAction,
    default_guidance_action_catalog,
)
from guojing.domain.guidance_actions import (
    ApprovedGuidanceAction,
    GuidanceAuthorization,
    authorize_guidance_action,
)
from guojing.domain.tutorials.models import RiskLevel


def test_only_low_risk_actions_resolve_to_automated_guidance() -> None:
    guidance = default_guidance_action_catalog().resolve(("general.observe_page",))

    assert guidance.steps[0].step_id == "general.observe_page"


@pytest.mark.parametrize(
    ("risk_level", "expected"),
    (
        (RiskLevel.LOW, GuidanceAuthorization.ALLOW),
        (RiskLevel.SENSITIVE, GuidanceAuthorization.STOP_AND_CONFIRM),
        (RiskLevel.FINANCIAL, GuidanceAuthorization.REQUIRE_HUMAN_REVIEW),
        (RiskLevel.IRREVERSIBLE, GuidanceAuthorization.REQUIRE_HUMAN_REVIEW),
    ),
)
def test_risk_authorization_does_not_depend_on_instruction_wording(
    risk_level: RiskLevel,
    expected: GuidanceAuthorization,
) -> None:
    assert authorize_guidance_action(risk_level) is expected


def test_financial_action_id_cannot_be_resolved_even_with_benign_text() -> None:
    catalog = GuidanceActionCatalog(
        (
            ApprovedGuidanceAction(
                action_id="wallet.benign_label",
                title="继续",
                instruction="请看一下这个按钮。",
                risk_level=RiskLevel.FINANCIAL,
            ),
        ),
    )

    with pytest.raises(UnknownGuidanceAction, match="require_human_review"):
        catalog.resolve(("wallet.benign_label",))
