package com.xisha.guojing.ui.detail

import com.xisha.guojing.model.AppIdentity
import com.xisha.guojing.model.PublishedTutorialDetail
import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.model.TutorialNode
import com.xisha.guojing.model.VerificationStatus
import org.junit.Assert.assertTrue
import org.junit.Test

class TutorialSafetyPresentationTest {
    @Test
    fun local_only_graph_is_presented_as_manual_and_startable() {
        val graph = TutorialGraph("1.0", "camera", "相机", AppIdentity("camera", "1", 1), "start", listOf(TutorialNode("start", "开始", emptyList(), PrivacyMode.LocalOnly, VerificationStatus.Verified, 1)), emptyList())
        val presentation = PublishedTutorialDetail(1, "2026-08-30T00:00:00Z", graph).safetyPresentation()
        assertTrue(presentation.canStart)
        assertTrue(presentation.manualActionLabel.contains("亲自"))
    }
}
