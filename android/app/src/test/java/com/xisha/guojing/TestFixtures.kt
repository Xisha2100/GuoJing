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
import com.xisha.guojing.model.TutorialTransition
import com.xisha.guojing.model.VerificationStatus

fun testTutorialDetail(
    transitions: List<TutorialTransition> = listOf(testTransition()),
    nodes: List<TutorialNode> = listOf(
        testNode("chat_list", "微信聊天列表"),
        testNode("conversation", "家人聊天页"),
    ),
): PublishedTutorialDetail = PublishedTutorialDetail(
    revisionNumber = 3,
    publishedAt = "2026-08-09T07:00:00Z",
    graph = TutorialGraph(
        schemaVersion = "1.0",
        graphId = "wechat_open_family_chat",
        title = "打开家人微信聊天",
        recordedApp = AppIdentity(
            packageName = "com.tencent.mm",
            versionName = "8.0.60",
            versionCode = 2600,
        ),
        startNodeId = "chat_list",
        nodes = nodes,
        transitions = transitions,
    ),
)

fun testNode(
    nodeId: String,
    title: String = nodeId,
    verificationStatus: VerificationStatus = VerificationStatus.Verified,
): TutorialNode = TutorialNode(
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
    verificationStatus = verificationStatus,
    lastVerifiedVersionCode = if (verificationStatus == VerificationStatus.Verified) 2600 else null,
)

fun testTransition(
    transitionId: String = "open_chat",
    sourceNodeId: String = "chat_list",
    targetNodeId: String = "conversation",
    riskLevel: RiskLevel = RiskLevel.Low,
): TutorialTransition = TutorialTransition(
    transitionId = transitionId,
    sourceNodeId = sourceNodeId,
    targetNodeId = targetNodeId,
    actionKind = ActionKind.Tap,
    instruction = "点击“家人”聊天",
    riskLevel = riskLevel,
    targetAnchorId = "anchor_$sourceNodeId",
)
