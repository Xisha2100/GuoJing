package com.xisha.guojing.execution

import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.model.VerificationStatus
import com.xisha.guojing.testNode
import com.xisha.guojing.testTransition
import com.xisha.guojing.testTutorialDetail
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TutorialExecutionEngineTest {
    @Test
    fun linear_graph_advances_to_terminal_node() {
        val engine = TutorialExecutionEngine(testTutorialDetail().graph)

        val first = engine.start() as TutorialExecutionStage.Step
        val completed = engine.advance(first) as TutorialExecutionStage.Completed

        assertEquals(1, first.stepNumber)
        assertEquals("点击“家人”聊天", first.transition.instruction)
        assertEquals("conversation", completed.node.nodeId)
        assertEquals(listOf("open_chat"), completed.completedTransitionIds)
    }

    @Test
    fun multiple_outgoing_transitions_are_not_chosen_implicitly() {
        val detail = testTutorialDetail(
            nodes = listOf(
                testNode("chat_list"),
                testNode("conversation"),
                testNode("contacts"),
            ),
            transitions = listOf(
                testTransition(),
                testTransition(
                    transitionId = "open_contacts",
                    targetNodeId = "contacts",
                ),
            ),
        )

        val stage = TutorialExecutionEngine(detail.graph).start()

        assertEquals(
            ExecutionBlockReason.AmbiguousBranch,
            (stage as TutorialExecutionStage.Blocked).reason,
        )
    }

    @Test
    fun financial_transition_is_blocked_before_instruction_can_advance() {
        val detail = testTutorialDetail(
            transitions = listOf(testTransition(riskLevel = RiskLevel.Financial)),
        )

        val stage = TutorialExecutionEngine(detail.graph).start()

        val blocked = stage as TutorialExecutionStage.Blocked
        assertEquals(ExecutionBlockReason.HighRiskStep, blocked.reason)
        assertEquals(RiskLevel.Financial, blocked.transition?.riskLevel)
    }

    @Test
    fun stale_start_node_is_blocked() {
        val detail = testTutorialDetail(
            nodes = listOf(
                testNode("chat_list", verificationStatus = VerificationStatus.Stale),
                testNode("conversation"),
            ),
        )

        val stage = TutorialExecutionEngine(detail.graph).start()

        assertEquals(
            ExecutionBlockReason.StaleNode,
            (stage as TutorialExecutionStage.Blocked).reason,
        )
    }

    @Test
    fun repeated_cycle_requires_future_page_observation() {
        val detail = testTutorialDetail(
            transitions = listOf(
                testTransition(),
                testTransition(
                    transitionId = "back_to_list",
                    sourceNodeId = "conversation",
                    targetNodeId = "chat_list",
                ),
            ),
        )
        val engine = TutorialExecutionEngine(detail.graph)

        val first = engine.start() as TutorialExecutionStage.Step
        val second = engine.advance(first) as TutorialExecutionStage.Step
        val blocked = engine.advance(second) as TutorialExecutionStage.Blocked

        assertEquals(ExecutionBlockReason.CycleRequiresObservation, blocked.reason)
        assertTrue(blocked.completedTransitionIds.containsAll(listOf("open_chat", "back_to_list")))
    }

    @Test
    fun sensitive_transition_remains_user_controlled_but_is_not_hard_blocked() {
        val detail = testTutorialDetail(
            transitions = listOf(testTransition(riskLevel = RiskLevel.Sensitive)),
        )

        val stage = TutorialExecutionEngine(detail.graph).start()

        assertTrue(stage is TutorialExecutionStage.Step)
    }

    @Test
    fun invalid_graph_fails_closed_instead_of_crashing() {
        val detail = testTutorialDetail(
            nodes = emptyList(),
            transitions = emptyList(),
        )

        val stage = TutorialExecutionEngine(detail.graph).start()

        assertEquals(
            ExecutionBlockReason.InvalidGraph,
            (stage as TutorialExecutionStage.Blocked).reason,
        )
    }
}
