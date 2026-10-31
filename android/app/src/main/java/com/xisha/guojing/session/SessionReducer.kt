package com.xisha.guojing.session

import com.xisha.guojing.model.GuidanceDecision
import java.util.UUID

/** Pure state rules shared by live results, recovery, and local persistence. */
internal object SessionReducer {
    fun accepts(
        expectedGeneration: Long,
        currentGeneration: Long,
        expectedSessionId: UUID?,
        active: StoredAgentSession?,
        expectedRunId: UUID? = null,
    ): Boolean = expectedGeneration == currentGeneration &&
        (expectedSessionId == null || active?.sessionId == expectedSessionId) &&
        (expectedRunId == null || active?.currentRunId == expectedRunId)

    fun finish(
        session: StoredAgentSession,
        decision: GuidanceDecision?,
        incrementStep: Boolean,
    ): StoredAgentSession = session.copy(
        stepNumber = session.stepNumber + if (incrementStep) 1 else 0,
        currentRunId = null,
        eventsEndpoint = null,
        pendingTurnId = null,
        lastDecision = decision,
    )
}
