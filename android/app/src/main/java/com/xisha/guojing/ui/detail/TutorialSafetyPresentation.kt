package com.xisha.guojing.ui.detail

import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.PublishedTutorialDetail

data class TutorialSafetyPresentation(
    val privacyLabel: String,
    val manualActionLabel: String,
    val canStart: Boolean,
)

fun PublishedTutorialDetail.safetyPresentation(): TutorialSafetyPresentation {
    val localOnly = graph.nodes.all { it.privacyMode == PrivacyMode.LocalOnly }
    return TutorialSafetyPresentation(
        privacyLabel = if (localOnly) "仅在本机观察，不上传画面" else "请先确认隐私范围",
        manualActionLabel = "每一步都由你亲自操作",
        canStart = localOnly && graph.transitions.all { it.riskLevel.wireName == "low" },
    )
}
