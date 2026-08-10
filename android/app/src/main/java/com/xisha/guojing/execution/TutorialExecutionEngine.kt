package com.xisha.guojing.execution

import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.model.TutorialNode
import com.xisha.guojing.model.TutorialTransition
import com.xisha.guojing.model.VerificationStatus

sealed interface TutorialExecutionStage {
    val node: TutorialNode
    val completedTransitionIds: List<String>

    data class Step(
        override val node: TutorialNode,
        val transition: TutorialTransition,
        val stepNumber: Int,
        override val completedTransitionIds: List<String>,
    ) : TutorialExecutionStage

    data class Completed(
        override val node: TutorialNode,
        override val completedTransitionIds: List<String>,
    ) : TutorialExecutionStage

    data class Blocked(
        override val node: TutorialNode,
        val reason: ExecutionBlockReason,
        val transition: TutorialTransition? = null,
        override val completedTransitionIds: List<String>,
    ) : TutorialExecutionStage
}

enum class ExecutionBlockReason {
    StaleNode,
    AmbiguousBranch,
    HighRiskStep,
    CycleRequiresObservation,
    InvalidGraph,
}

/**
 * Deterministically walks a published graph without observing another app.
 *
 * It deliberately refuses decisions that need screen evidence: selecting one
 * of several branches, repeating a cycle, or crossing a high-risk transition.
 */
class TutorialExecutionEngine(
    private val graph: TutorialGraph,
) {
    fun start(): TutorialExecutionStage = evaluate(
        nodeId = graph.startNodeId,
        completedTransitionIds = emptyList(),
    )

    fun advance(stage: TutorialExecutionStage.Step): TutorialExecutionStage {
        val transition = stage.transition
        val currentOutgoing = graph.outgoingTransitions(stage.node.nodeId)
        if (transition !in currentOutgoing) {
            return TutorialExecutionStage.Blocked(
                node = stage.node,
                reason = ExecutionBlockReason.InvalidGraph,
                completedTransitionIds = stage.completedTransitionIds,
            )
        }
        return evaluate(
            nodeId = transition.targetNodeId,
            completedTransitionIds = stage.completedTransitionIds + transition.transitionId,
        )
    }

    private fun evaluate(
        nodeId: String,
        completedTransitionIds: List<String>,
    ): TutorialExecutionStage {
        val node = graph.node(nodeId)
            ?: return invalidStartFallback(completedTransitionIds)
        if (node.verificationStatus == VerificationStatus.Stale) {
            return TutorialExecutionStage.Blocked(
                node = node,
                reason = ExecutionBlockReason.StaleNode,
                completedTransitionIds = completedTransitionIds,
            )
        }

        val outgoing = graph.outgoingTransitions(node.nodeId)
        if (outgoing.isEmpty()) {
            return TutorialExecutionStage.Completed(
                node = node,
                completedTransitionIds = completedTransitionIds,
            )
        }
        if (outgoing.size > 1) {
            return TutorialExecutionStage.Blocked(
                node = node,
                reason = ExecutionBlockReason.AmbiguousBranch,
                completedTransitionIds = completedTransitionIds,
            )
        }

        val transition = outgoing.single()
        if (transition.transitionId in completedTransitionIds) {
            return TutorialExecutionStage.Blocked(
                node = node,
                reason = ExecutionBlockReason.CycleRequiresObservation,
                transition = transition,
                completedTransitionIds = completedTransitionIds,
            )
        }
        if (transition.riskLevel in HIGH_RISK_LEVELS) {
            return TutorialExecutionStage.Blocked(
                node = node,
                reason = ExecutionBlockReason.HighRiskStep,
                transition = transition,
                completedTransitionIds = completedTransitionIds,
            )
        }
        return TutorialExecutionStage.Step(
            node = node,
            transition = transition,
            stepNumber = completedTransitionIds.size + 1,
            completedTransitionIds = completedTransitionIds,
        )
    }

    private fun invalidStartFallback(
        completedTransitionIds: List<String>,
    ): TutorialExecutionStage.Blocked {
        val fallback = graph.nodes.firstOrNull() ?: EMPTY_NODE
        return TutorialExecutionStage.Blocked(
            node = fallback,
            reason = ExecutionBlockReason.InvalidGraph,
            completedTransitionIds = completedTransitionIds,
        )
    }

    private companion object {
        val HIGH_RISK_LEVELS = setOf(RiskLevel.Irreversible, RiskLevel.Financial)
        val EMPTY_NODE = TutorialNode(
            nodeId = "invalid",
            title = "教程数据无效",
            anchors = emptyList(),
            privacyMode = com.xisha.guojing.model.PrivacyMode.CapturePaused,
            verificationStatus = VerificationStatus.Stale,
            lastVerifiedVersionCode = null,
        )
    }
}
