package com.xisha.guojing.execution

import com.xisha.guojing.data.HelpRequestTutorialPlan
import com.xisha.guojing.model.PublishedTutorialDetail
import com.xisha.guojing.model.RiskLevel

sealed interface TutorialPlanLaunchDecision {
    data object Allowed : TutorialPlanLaunchDecision
    data class Blocked(val reason: String) : TutorialPlanLaunchDecision
}

/** Ensures a server plan cannot widen the locally downloaded tutorial graph. */
class HelpRequestTutorialLaunchGuard {
    fun evaluate(
        plan: HelpRequestTutorialPlan,
        tutorial: PublishedTutorialDetail,
    ): TutorialPlanLaunchDecision {
        if (plan.graphId != tutorial.graph.graphId || plan.revisionNumber != tutorial.revisionNumber) {
            return TutorialPlanLaunchDecision.Blocked("教程版本已变化，请重新求助")
        }
        if (tutorial.graph.node(plan.nodeId) == null) {
            return TutorialPlanLaunchDecision.Blocked("教程起始页面不存在")
        }
        val transitions = tutorial.graph.outgoingTransitions(plan.nodeId)
        val allowed = transitions.filter { it.transitionId in plan.allowedTransitionIds }
        if (allowed.size != plan.allowedTransitionIds.size || allowed.any { it.riskLevel != RiskLevel.Low }) {
            return TutorialPlanLaunchDecision.Blocked("教程步骤未通过本地安全校验")
        }
        return TutorialPlanLaunchDecision.Allowed
    }
}
