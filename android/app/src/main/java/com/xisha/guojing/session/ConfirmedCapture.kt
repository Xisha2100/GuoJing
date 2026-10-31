package com.xisha.guojing.session

import com.xisha.guojing.data.AgentHttpException
import com.xisha.guojing.data.AgentRepository
import com.xisha.guojing.model.AgentRunAccepted
import com.xisha.guojing.model.AgentSessionHandle
import com.xisha.guojing.model.CaptureGeometry
import com.xisha.guojing.model.TargetApp
import com.xisha.guojing.observation.ScreenCapturePort
import java.util.UUID
import kotlinx.coroutines.CancellationException

internal data class SubmittedTurn(
    val session: StoredAgentSession,
    val geometry: CaptureGeometry,
    val accepted: AgentRunAccepted,
)

/** One invocation per user action. Owns and erases the image before returning metadata. */
internal class ConfirmedCapture(
    private val capture: ScreenCapturePort,
    private val repository: AgentRepository,
    private val recovery: RunRecovery,
) {
    suspend fun submit(
        session: StoredAgentSession,
        target: TargetApp,
        ensureCurrent: suspend () -> Unit,
        persist: suspend (StoredAgentSession) -> Unit,
    ): SubmittedTurn {
        ensureCurrent()
        check(capture.isTargetCurrent(target))
        val screenshot = capture.capture(session.targetPackage)
        try {
            ensureCurrent()
            check(capture.isTargetCurrent(target))
            val geometry = CaptureGeometry(
                screenshot.displayWidth, screenshot.displayHeight, screenshot.rotation, screenshot.windowId,
            )
            val turnId = UUID.randomUUID()
            val pending = session.copy(
                pendingTurnId = turnId,
                displayWidth = geometry.displayWidth,
                displayHeight = geometry.displayHeight,
                rotation = geometry.rotation,
            )
            persist(pending) // The turn ID is durable before any upload, never the image.
            ensureCurrent()
            check(capture.isTargetCurrent(target.copy(windowId = geometry.windowId)))
            check(capture.isDisplayCurrent(
                session.targetPackage, geometry.displayWidth, geometry.displayHeight, geometry.rotation,
            ))
            val accepted = try {
                repository.createRun(
                    AgentSessionHandle(session.sessionId, session.accessToken), turnId, screenshot,
                )
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                screenshot.erase()
                ensureCurrent()
                if (error is AgentHttpException) throw error
                val found = recovery.findUploaded(pending, turnId)
                AgentRunAccepted(found.runId, found.status, "/api/v1/agent/runs/${found.runId}/events")
            }
            ensureCurrent()
            val submitted = pending.copy(
                currentRunId = accepted.runId, eventsEndpoint = accepted.eventsEndpoint,
            )
            screenshot.erase()
            persist(submitted)
            return SubmittedTurn(submitted, geometry, accepted)
        } finally {
            screenshot.erase()
        }
    }
}
