package com.xisha.guojing.session

import com.xisha.guojing.data.AgentHttpException
import com.xisha.guojing.data.AgentRepository
import com.xisha.guojing.model.AgentProtocolException
import com.xisha.guojing.model.AgentRunSnapshot
import com.xisha.guojing.model.AgentSessionHandle
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.withTimeout

/** Read-only recovery. It never cancels a found run, uploads, or requests a screenshot. */
internal class RunRecovery(private val repository: AgentRepository) {
    suspend fun findPending(session: StoredAgentSession): AgentRunSnapshot? {
        return try {
            val snapshot = session.currentRunId?.let {
                repository.getRun(it, session.accessToken)
            } ?: session.pendingTurnId?.let {
                repository.getTurn(AgentSessionHandle(session.sessionId, session.accessToken), it)
            } ?: return null
            currentCoroutineContext().ensureActive()
            validate(snapshot, session, session.currentRunId ?: snapshot.runId)
        } catch (error: AgentHttpException) {
            if (error.statusCode == 404) null else throw error
        }
    }

    suspend fun findUploaded(session: StoredAgentSession, turnId: UUID): AgentRunSnapshot {
        val snapshot = repository.getTurn(
            AgentSessionHandle(session.sessionId, session.accessToken), turnId,
        )
        currentCoroutineContext().ensureActive()
        return validate(snapshot, session, snapshot.runId)
    }

    suspend fun resume(session: StoredAgentSession, runId: UUID): AgentRunSnapshot =
        withTimeout(WAIT_MILLIS) {
            val current = validate(repository.getRun(runId, session.accessToken), session, runId)
            if (current.status.isTerminal) current else awaitTerminal(
                session, runId, session.eventsEndpoint ?: "/api/v1/agent/runs/$runId/events",
            )
        }

    suspend fun awaitTerminal(
        session: StoredAgentSession,
        runId: UUID,
        endpoint: String,
    ): AgentRunSnapshot = withTimeout(WAIT_MILLIS) {
        try {
            withTimeout(100_000L) {
                repository.observeRun(endpoint, session.accessToken)
                    .onEach { validate(it, session, runId) }
                    .first { it.status.isTerminal }
            }
        } catch (_: TimeoutCancellationException) {
            currentCoroutineContext().ensureActive()
            poll(session, runId)
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            if (isTerminalError(error)) throw error
            poll(session, runId)
        }
    }

    private suspend fun poll(session: StoredAgentSession, runId: UUID): AgentRunSnapshot {
        var delayMillis = 1_000L
        while (true) {
            currentCoroutineContext().ensureActive()
            try {
                val snapshot = validate(repository.getRun(runId, session.accessToken), session, runId)
                if (snapshot.status.isTerminal) return snapshot
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                if (isTerminalError(error)) throw error
            }
            delay(delayMillis)
            delayMillis = (delayMillis * 2).coerceAtMost(15_000L)
        }
    }

    private fun isTerminalError(error: Exception) = error is AgentProtocolException ||
        (error is AgentHttpException && error.statusCode in setOf(401, 403, 404))

    private fun validate(
        snapshot: AgentRunSnapshot,
        session: StoredAgentSession,
        runId: UUID,
    ): AgentRunSnapshot {
        if (snapshot.runId != runId || snapshot.sessionId != session.sessionId) {
            throw AgentProtocolException("Run identity does not match the active session")
        }
        return snapshot
    }

    private companion object {
        const val WAIT_MILLIS = 150_000L
    }
}
