"""First-party MVP scenario templates for the most common elderly-user tasks."""

from dataclasses import dataclass

from guojing.domain.tutorials.models import (
    ActionKind,
    AnchorRole,
    AppIdentity,
    PrivacyMode,
    RiskLevel,
    ScreenAnchor,
    SemanticLocator,
    TutorialGraph,
    TutorialNode,
    TutorialTransition,
    VerificationStatus,
)


@dataclass(frozen=True, slots=True)
class ScenarioTemplate:
    template_id: str
    title: str
    package_name: str
    action_label: str
    risk_level: RiskLevel


MVP_SCENARIOS: tuple[ScenarioTemplate, ...] = (
    ScenarioTemplate(
        "wechat_add_friend", "微信添加好友", "com.tencent.mm", "添加好友", RiskLevel.SENSITIVE
    ),
    ScenarioTemplate(
        "wechat_create_group", "微信拉群", "com.tencent.mm", "发起群聊", RiskLevel.SENSITIVE
    ),
    ScenarioTemplate(
        "wechat_send_voice", "微信发语音", "com.tencent.mm", "按住说话", RiskLevel.SENSITIVE
    ),
    ScenarioTemplate(
        "wechat_receive_red_packet", "微信收红包", "com.tencent.mm", "打开红包", RiskLevel.FINANCIAL
    ),
    ScenarioTemplate(
        "wechat_offline_payment",
        "微信线下支付",
        "com.tencent.mm",
        "出示付款码",
        RiskLevel.FINANCIAL,
    ),
    ScenarioTemplate(
        "wechat_check_balance", "微信确认余额", "com.tencent.mm", "查看余额", RiskLevel.FINANCIAL
    ),
    ScenarioTemplate(
        "douyin_search_video", "抖音搜索视频", "com.ss.android.ugc.aweme", "搜索内容", RiskLevel.LOW
    ),
    ScenarioTemplate(
        "taobao_choose_product", "网购选择商品", "com.taobao.taobao", "查看商品评价", RiskLevel.LOW
    ),
    ScenarioTemplate(
        "didi_call_ride", "滴滴打车", "com.didi.theone", "设置目的地", RiskLevel.SENSITIVE
    ),
    ScenarioTemplate(
        "amap_start_navigation",
        "高德地图开始导航",
        "com.autonavi.minimap",
        "开始导航",
        RiskLevel.LOW,
    ),
    ScenarioTemplate(
        "system_make_call", "系统拨打电话", "com.android.dialer", "拨打电话", RiskLevel.SENSITIVE
    ),
    ScenarioTemplate(
        "system_save_contact",
        "记录通讯录",
        "com.android.contacts",
        "保存联系人",
        RiskLevel.SENSITIVE,
    ),
    ScenarioTemplate(
        "system_view_gallery",
        "翻看图库照片",
        "com.google.android.apps.photos",
        "打开照片",
        RiskLevel.LOW,
    ),
)


def scenario_template(template_id: str) -> TutorialGraph:
    """Build a two-state draft; device recording must replace generic anchors."""
    try:
        spec = next(value for value in MVP_SCENARIOS if value.template_id == template_id)
    except StopIteration as error:
        raise ValueError("unknown tutorial scenario template") from error
    source_id = f"{spec.template_id}_start"
    target_id = f"{spec.template_id}_done"
    source_anchor = ScreenAnchor(
        anchor_id="primary_action",
        role=AnchorRole.REQUIRED,
        locator=SemanticLocator(text=spec.action_label),
    )
    target_anchor = ScreenAnchor(
        anchor_id="result",
        role=AnchorRole.REQUIRED,
        locator=SemanticLocator(text="已完成"),
    )
    return TutorialGraph(
        graph_id=spec.template_id,
        title=spec.title,
        recorded_app=AppIdentity(spec.package_name, "recorded-device", 1),
        start_node_id=source_id,
        nodes=(
            TutorialNode(
                source_id,
                f"{spec.title}起始页面",
                (source_anchor,),
                PrivacyMode.LOCAL_ONLY,
                VerificationStatus.PROVISIONAL,
                None,
            ),
            TutorialNode(
                target_id,
                f"{spec.title}完成页面",
                (target_anchor,),
                PrivacyMode.LOCAL_ONLY,
                VerificationStatus.PROVISIONAL,
                None,
            ),
        ),
        transitions=(
            TutorialTransition(
                f"{spec.template_id}_action",
                source_id,
                target_id,
                ActionKind.TAP,
                f"请你亲自操作: {spec.action_label}。",
                spec.risk_level,
                "primary_action",
            ),
        ),
    )
