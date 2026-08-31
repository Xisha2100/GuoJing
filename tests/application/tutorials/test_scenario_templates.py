from guojing.application.tutorials.scenario_templates import MVP_SCENARIOS, scenario_template
from guojing.domain.tutorials.models import PrivacyMode, RiskLevel, VerificationStatus


def test_mvp_catalog_covers_the_confirmed_user_scenarios() -> None:
    assert len(MVP_SCENARIOS) == 13
    assert {value.template_id for value in MVP_SCENARIOS} >= {
        "wechat_add_friend",
        "wechat_create_group",
        "wechat_send_voice",
        "wechat_receive_red_packet",
        "wechat_offline_payment",
        "wechat_check_balance",
        "douyin_search_video",
        "taobao_choose_product",
        "didi_call_ride",
        "amap_start_navigation",
        "system_make_call",
        "system_save_contact",
        "system_view_gallery",
    }


def test_financial_scenario_stays_provisional_and_local() -> None:
    graph = scenario_template("wechat_offline_payment")
    assert graph.nodes[0].privacy_mode is PrivacyMode.LOCAL_ONLY
    assert graph.nodes[0].verification_status is VerificationStatus.PROVISIONAL
    assert graph.transitions[0].risk_level is RiskLevel.FINANCIAL
