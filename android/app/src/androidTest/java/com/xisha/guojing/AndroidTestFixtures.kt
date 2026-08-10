package com.xisha.guojing

import com.xisha.guojing.model.ActionKind
import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.model.AppIdentity
import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.PublishedTutorialDetail
import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.model.ScreenAnchor
import com.xisha.guojing.model.SemanticLocator
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.model.TutorialNode
import com.xisha.guojing.model.TutorialSummary
import com.xisha.guojing.model.TutorialTransition
import com.xisha.guojing.model.VerificationStatus

val androidTestSummary = TutorialSummary(
    graphId = "wechat_open_family_chat",
    title = "打开家人微信聊天",
    packageName = "com.tencent.mm",
    recordedVersionName = "8.0.60",
    recordedVersionCode = 2600,
    revisionNumber = 3,
    publishedAt = "2026-08-09T07:00:00Z",
)

fun androidTestDetail(
    riskLevel: RiskLevel = RiskLevel.Low,
): PublishedTutorialDetail {
    val start = androidTestNode("chat_list", "微信聊天列表")
    val end = androidTestNode("conversation", "家人聊天页")
    return PublishedTutorialDetail(
        revisionNumber = 3,
        publishedAt = "2026-08-09T07:00:00Z",
        graph = TutorialGraph(
            schemaVersion = "1.0",
            graphId = androidTestSummary.graphId,
            title = androidTestSummary.title,
            recordedApp = AppIdentity(
                packageName = "com.tencent.mm",
                versionName = "8.0.60",
                versionCode = 2600,
            ),
            startNodeId = start.nodeId,
            nodes = listOf(start, end),
            transitions = listOf(
                TutorialTransition(
                    transitionId = "open_family_chat",
                    sourceNodeId = start.nodeId,
                    targetNodeId = end.nodeId,
                    actionKind = ActionKind.Tap,
                    instruction = "点击“家人”聊天",
                    riskLevel = riskLevel,
                    targetAnchorId = start.anchors.single().anchorId,
                ),
            ),
        ),
    )
}

private fun androidTestNode(nodeId: String, title: String): TutorialNode = TutorialNode(
    nodeId = nodeId,
    title = title,
    anchors = listOf(
        ScreenAnchor(
            anchorId = "anchor_$nodeId",
            role = AnchorRole.Required,
            locator = SemanticLocator(
                resourceId = null,
                contentDescription = null,
                text = title,
                ocrText = null,
            ),
            relativeConstraints = emptyList(),
            boundsFallback = null,
        ),
    ),
    privacyMode = PrivacyMode.LocalOnly,
    verificationStatus = VerificationStatus.Verified,
    lastVerifiedVersionCode = 2600,
)
