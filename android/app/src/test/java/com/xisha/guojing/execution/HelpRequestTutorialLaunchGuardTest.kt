package com.xisha.guojing.execution

import com.xisha.guojing.data.HelpRequestTutorialPlan
import com.xisha.guojing.model.ActionKind
import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.model.AppIdentity
import com.xisha.guojing.model.PublishedTutorialDetail
import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.model.ScreenAnchor
import com.xisha.guojing.model.SemanticLocator
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.model.TutorialNode
import com.xisha.guojing.model.TutorialTransition
import com.xisha.guojing.model.VerificationStatus
import org.junit.Assert.assertEquals
import org.junit.Test

class HelpRequestTutorialLaunchGuardTest {
    @Test
    fun blocks_a_plan_that_references_a_financial_transition() {
        val node = TutorialNode("start", "开始", listOf(ScreenAnchor("a", AnchorRole.Required, SemanticLocator(null, "a", null, null), emptyList(), null)), PrivacyMode.LocalOnly, VerificationStatus.Verified, 1)
        val graph = TutorialGraph("1.0", "camera", "相机", AppIdentity("camera", "1", 1), "start", listOf(node), listOf(TutorialTransition("pay", "start", "start", ActionKind.Tap, "点击", RiskLevel.Financial, "a")))
        val tutorial = PublishedTutorialDetail(1, "2026-08-30T00:00:00Z", graph)
        val plan = HelpRequestTutorialPlan("camera", "start", 1, "verified", listOf("pay"))

        assertEquals(TutorialPlanLaunchDecision.Blocked("教程步骤未通过本地安全校验"), HelpRequestTutorialLaunchGuard().evaluate(plan, tutorial))
    }
}
