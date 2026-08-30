"""A reviewed starter graph for the system Camera capture tutorial."""

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


def camera_capture_tutorial() -> TutorialGraph:
    """Return a draft graph; an administrator must still verify and publish it."""
    camera = AppIdentity("com.android.camera", "recorded-device", 1)
    preview = TutorialNode(
        node_id="camera_preview",
        title="相机预览页面",
        anchors=(
            ScreenAnchor(
                anchor_id="shutter_button",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(content_description="拍照"),
            ),
        ),
        privacy_mode=PrivacyMode.LOCAL_ONLY,
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=1,
    )
    captured = TutorialNode(
        node_id="photo_captured",
        title="已拍摄照片",
        anchors=(
            ScreenAnchor(
                anchor_id="photo_thumbnail",
                role=AnchorRole.REQUIRED,
                locator=SemanticLocator(content_description="查看最近照片"),
            ),
        ),
        privacy_mode=PrivacyMode.LOCAL_ONLY,
        verification_status=VerificationStatus.VERIFIED,
        last_verified_version_code=1,
    )
    return TutorialGraph(
        graph_id="system_camera_take_photo",
        title="使用相机拍照",
        recorded_app=camera,
        start_node_id=preview.node_id,
        nodes=(preview, captured),
        transitions=(
            TutorialTransition(
                transition_id="take_photo",
                source_node_id=preview.node_id,
                target_node_id=captured.node_id,
                action_kind=ActionKind.TAP,
                instruction="请你亲自点击屏幕下方圆形拍照按钮。",
                risk_level=RiskLevel.LOW,
                target_anchor_id="shutter_button",
            ),
        ),
    )
