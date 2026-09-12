package com.xisha.guojing.session

import com.xisha.guojing.data.AgentHttpException
import com.xisha.guojing.data.AgentRepository
import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.guidance.OverlayActions
import com.xisha.guojing.guidance.OverlayPresentation
import com.xisha.guojing.model.AgentProtocolException
import com.xisha.guojing.model.AgentRunSnapshot
import com.xisha.guojing.model.AgentRunStatus
import com.xisha.guojing.model.AgentSessionHandle
import com.xisha.guojing.model.GuidanceDecision
import com.xisha.guojing.model.GuidanceStatus
import com.xisha.guojing.model.TargetApp
import com.xisha.guojing.observation.ScreenCapturePort
import com.xisha.guojing.platform.TargetAppCatalog
import com.xisha.guojing.platform.TargetAppLauncher
import com.xisha.guojing.speech.SpeechPort
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout

enum class ClientPhase {
    Setup,
    CreatingSession,
    ReadyToCapture,
    Capturing,
    WaitingForAgent,
    ShowingGuidance,
    Retry,
    Completed,
}

data class AgentClientUiState(
    val phase: ClientPhase = ClientPhase.Setup,
    val availableApps: List<TargetApp> = emptyList(),
    val selectedPackage: String? = null,
    val goal: String = "",
    val uploadConsent: Boolean = false,
    val accessibilityConnected: Boolean = false,
    val targetLabel: String? = null,
    val stepNumber: Int = 0,
    val instruction: String? = null,
    val confidence: Double? = null,
    val message: String? = null,
) {
    val canStart: Boolean
        get() = phase == ClientPhase.Setup &&
            accessibilityConnected &&
            selectedPackage != null &&
            goal.isNotBlank() &&
            uploadConsent
}

class AgentSessionController(
    private val repository: AgentRepository,
    private val capture: ScreenCapturePort,
    private val overlay: GuidanceOverlayPort,
    private val speech: SpeechPort,
    private val store: ActiveSessionStore,
    private val appCatalog: TargetAppCatalog,
    private val appLauncher: TargetAppLauncher,
    private val scope: CoroutineScope,
    private val nowEpochSeconds: () -> Long = { Instant.now().epochSecond },
) : OverlayActions {
    private val mutableUiState = MutableStateFlow(AgentClientUiState())
    val uiState: StateFlow<AgentClientUiState> = mutableUiState.asStateFlow()

    private var active: StoredAgentSession? = null
    private var runJob: Job? = null
    private var lastSpokenText: String? = null

    init {
        scope.launch {
            capture.connected.collect { connected ->
                mutableUiState.update { it.copy(accessibilityConnected = connected) }
            }
        }
        scope.launch { initialize() }
    }

    fun updateGoal(value: String) {
        if (active != null) return
        mutableUiState.update { it.copy(goal = value.take(MAX_GOAL_LENGTH), message = null) }
    }

    fun selectApp(packageName: String) {
        if (active != null) return
        if (mutableUiState.value.availableApps.none { it.packageName == packageName }) return
        mutableUiState.update { it.copy(selectedPackage = packageName, message = null) }
    }

    fun setUploadConsent(value: Boolean) {
        if (active != null) return
        mutableUiState.update { it.copy(uploadConsent = value, message = null) }
    }

    fun startSession() {
        if (!mutableUiState.value.canStart || active != null) return
        mutableUiState.update { it.copy(phase = ClientPhase.CreatingSession, message = null) }
        scope.launch { createSession() }
    }

    fun openTargetApp() {
        active?.let { session ->
            if (!appLauncher.launch(session.targetPackage)) {
                mutableUiState.update { it.copy(message = "无法打开目标应用，请确认应用仍已安装") }
            }
        }
    }

    override fun onPrimaryAction() {
        if (mutableUiState.value.phase == ClientPhase.Completed) {
            endSession()
        } else {
            requestGuidance()
        }
    }

    override fun onReplay() {
        lastSpokenText?.let(speech::speak)
    }

    override fun onEndSession() {
        endSession()
    }

    fun requestGuidance() {
        if (runJob?.isActive == true) return
        if (mutableUiState.value.phase !in setOf(
                ClientPhase.ReadyToCapture,
                ClientPhase.ShowingGuidance,
                ClientPhase.Retry,
            )
        ) {
            return
        }
        runJob = scope.launch { captureAndRun() }
    }

    fun endSession() {
        val session = active ?: return
        runJob?.cancel()
        active = null
        speech.stop()
        overlay.hide()
        lastSpokenText = null
        mutableUiState.update {
            AgentClientUiState(
                availableApps = it.availableApps,
                accessibilityConnected = it.accessibilityConnected,
            )
        }
        runJob = scope.launch {
            store.clear()
            session.currentRunId?.let { runId ->
                runCatching { repository.cancelRun(runId, session.accessToken) }
            }
            runCatching { repository.closeSession(session.sessionId, session.accessToken) }
        }
    }

    private suspend fun initialize() {
        val apps = runCatching { appCatalog.listLaunchableApps() }.getOrDefault(emptyList())
        mutableUiState.update { it.copy(availableApps = apps) }
        val restored = store.load() ?: return
        if (nowEpochSeconds() - restored.createdAtEpochSeconds >= SESSION_TTL_SECONDS) {
            store.clear()
            return
        }
        active = restored
        showRestored(restored)
        restored.currentRunId?.let { runId ->
            runJob = scope.launch { resumeRun(restored, runId) }
        }
    }

    private suspend fun createSession() {
        val state = mutableUiState.value
        val app = state.availableApps.firstOrNull { it.packageName == state.selectedPackage }
            ?: return
        try {
            val handle = repository.createSession(
                clientSessionId = UUID.randomUUID(),
                goal = state.goal.trim(),
                targetPackage = app.packageName,
            )
            val session = StoredAgentSession(
                sessionId = handle.sessionId,
                accessToken = handle.accessToken,
                goal = state.goal.trim(),
                targetPackage = app.packageName,
                targetLabel = app.label,
                createdAtEpochSeconds = nowEpochSeconds(),
                stepNumber = 0,
                currentRunId = null,
                eventsEndpoint = null,
                lastDecision = null,
                displayWidth = null,
                displayHeight = null,
                rotation = null,
            )
            active = session
            store.save(session)
            mutableUiState.update {
                it.copy(
                    phase = ClientPhase.ReadyToCapture,
                    targetLabel = app.label,
                    stepNumber = 0,
                    instruction = null,
                    confidence = null,
                    message = null,
                )
            }
            overlay.present(OverlayPresentation.Ready(app.packageName, app.label))
            if (!appLauncher.launch(app.packageName)) {
                showRetry("无法自动打开目标应用，请手动打开后重试")
            }
        } catch (error: Exception) {
            mutableUiState.update {
                it.copy(
                    phase = ClientPhase.Setup,
                    message = userMessage(error, "创建会话失败，请检查网络后重试"),
                )
            }
        }
    }

    private suspend fun captureAndRun() {
        var session = active ?: return
        session.currentRunId?.let { previousRunId ->
            runCatching { repository.cancelRun(previousRunId, session.accessToken) }
            session = session.copy(currentRunId = null, eventsEndpoint = null)
            active = session
            store.save(session)
        }
        speech.stop()
        mutableUiState.update { it.copy(phase = ClientPhase.Capturing, message = null) }
        overlay.present(OverlayPresentation.Loading(session.targetPackage))
        val screenshot = try {
            capture.capture(session.targetPackage)
        } catch (error: CancellationException) {
            throw error
        } catch (_: Exception) {
            showRetry("请先打开 ${session.targetLabel}，保持界面稳定后重试")
            return
        }
        try {
            val accepted = repository.createRun(
                session = AgentSessionHandle(session.sessionId, session.accessToken),
                clientTurnId = UUID.randomUUID(),
                screenshot = screenshot,
            )
            screenshot.erase()
            session = session.copy(
                currentRunId = accepted.runId,
                eventsEndpoint = accepted.eventsEndpoint,
                displayWidth = screenshot.displayWidth,
                displayHeight = screenshot.displayHeight,
                rotation = screenshot.rotation,
            )
            active = session
            store.save(session)
            mutableUiState.update { it.copy(phase = ClientPhase.WaitingForAgent) }
            val terminal = awaitTerminal(session, accepted.runId, accepted.eventsEndpoint)
            applyTerminal(session, screenshot, terminal)
        } catch (_: TimeoutCancellationException) {
            showRetry("等待识别结果超时，请稍后重新识别")
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            showRetry(userMessage(error, "识别服务暂时不可用，请稍后重试"))
        } finally {
            screenshot.erase()
        }
    }

    private suspend fun awaitTerminal(
        session: StoredAgentSession,
        runId: UUID,
        eventsEndpoint: String,
    ): AgentRunSnapshot = try {
        withTimeout(RUN_WAIT_TIMEOUT_MILLIS) {
            repository.observeRun(eventsEndpoint, session.accessToken)
                .first { it.status.isTerminal }
        }
    } catch (_: TimeoutCancellationException) {
        pollTerminal(session, runId)
    } catch (error: CancellationException) {
        throw error
    } catch (_: Exception) {
        pollTerminal(session, runId)
    }

    private suspend fun pollTerminal(
        session: StoredAgentSession,
        runId: UUID,
    ): AgentRunSnapshot {
        var delayMillis = 1_000L
        return withTimeout(RUN_WAIT_TIMEOUT_MILLIS) {
            while (true) {
                val snapshot = repository.getRun(runId, session.accessToken)
                if (snapshot.status.isTerminal) return@withTimeout snapshot
                delay(delayMillis)
                delayMillis = (delayMillis * 2).coerceAtMost(15_000L)
            }
            error("unreachable")
        }
    }

    private suspend fun applyTerminal(
        session: StoredAgentSession,
        screenshot: com.xisha.guojing.model.CapturedScreen,
        snapshot: AgentRunSnapshot,
    ) {
        require(snapshot.runId == requireNotNull(session.currentRunId))
        require(snapshot.sessionId == session.sessionId)
        if (snapshot.status != AgentRunStatus.Completed) {
            clearCompletedRun(session)
            showRetry(runFailureMessage(snapshot))
            return
        }
        val decision = snapshot.result ?: throw AgentProtocolException("Missing result")
        when (decision.status) {
            GuidanceStatus.Continue -> {
                if (!capture.isDisplayCurrent(
                        session.targetPackage,
                        screenshot.displayWidth,
                        screenshot.displayHeight,
                        screenshot.rotation,
                    )
                ) {
                    clearCompletedRun(session)
                    showRetry("界面已发生变化，请重新识别")
                    return
                }
                val next = completedStep(session, decision)
                val instruction = requireNotNull(decision.instruction)
                overlay.present(
                    OverlayPresentation.Guidance(
                        targetPackage = session.targetPackage,
                        stepNumber = next.stepNumber,
                        instruction = instruction,
                        target = requireNotNull(decision.target),
                        displayWidth = screenshot.displayWidth,
                        displayHeight = screenshot.displayHeight,
                        rotation = screenshot.rotation,
                    ),
                )
                lastSpokenText = instruction
                speech.speak(instruction)
                mutableUiState.update {
                    it.copy(
                        phase = ClientPhase.ShowingGuidance,
                        stepNumber = next.stepNumber,
                        instruction = instruction,
                        confidence = decision.confidence,
                        message = null,
                    )
                }
            }

            GuidanceStatus.CannotDetermine -> {
                clearCompletedRun(session, decision)
                showRetry(decision.instruction ?: "当前界面无法确定，请保持页面稳定后重试")
            }

            GuidanceStatus.Completed -> {
                val next = completedStep(session, decision)
                val message = decision.instruction ?: "目标已经完成"
                overlay.present(OverlayPresentation.Completed(session.targetPackage, message))
                lastSpokenText = message
                speech.speak(message)
                mutableUiState.update {
                    it.copy(
                        phase = ClientPhase.Completed,
                        stepNumber = next.stepNumber,
                        instruction = message,
                        confidence = decision.confidence,
                        message = null,
                    )
                }
            }
        }
    }

    private suspend fun completedStep(
        session: StoredAgentSession,
        decision: GuidanceDecision,
    ): StoredAgentSession {
        val next = session.copy(
            stepNumber = session.stepNumber + 1,
            currentRunId = null,
            eventsEndpoint = null,
            lastDecision = decision,
        )
        active = next
        store.save(next)
        return next
    }

    private suspend fun clearCompletedRun(
        session: StoredAgentSession,
        decision: GuidanceDecision? = null,
    ) {
        val next = session.copy(
            currentRunId = null,
            eventsEndpoint = null,
            lastDecision = decision,
        )
        active = next
        store.save(next)
    }

    private suspend fun resumeRun(session: StoredAgentSession, runId: UUID) {
        mutableUiState.update { it.copy(phase = ClientPhase.WaitingForAgent) }
        overlay.present(OverlayPresentation.Loading(session.targetPackage))
        try {
            val current = repository.getRun(runId, session.accessToken)
            require(current.runId == runId && current.sessionId == session.sessionId)
            val terminal = if (current.status.isTerminal) {
                current
            } else {
                awaitTerminal(
                    session,
                    runId,
                    session.eventsEndpoint ?: "/api/v1/agent/runs/$runId/events",
                )
            }
            if (terminal.status == AgentRunStatus.Completed && terminal.result != null) {
                val updated = session.copy(
                    currentRunId = null,
                    eventsEndpoint = null,
                    lastDecision = terminal.result,
                    stepNumber = session.stepNumber + 1,
                )
                active = updated
                store.save(updated)
                showRestored(updated)
            } else {
                clearCompletedRun(session)
                showRetry(runFailureMessage(terminal))
            }
        } catch (_: TimeoutCancellationException) {
            showRetry("恢复识别结果超时，请稍后重新识别")
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            if (error is AgentHttpException && error.statusCode == 404) {
                store.clear()
                active = null
                overlay.hide()
                mutableUiState.update {
                    AgentClientUiState(
                        availableApps = it.availableApps,
                        accessibilityConnected = it.accessibilityConnected,
                        message = "原会话已失效，请重新开始",
                    )
                }
            } else {
                showRetry("恢复会话失败，请检查网络后重试")
            }
        }
    }

    private fun showRestored(session: StoredAgentSession) {
        val decision = session.lastDecision
        if (decision?.status == GuidanceStatus.Continue) {
            overlay.present(OverlayPresentation.Ready(session.targetPackage, session.targetLabel))
            lastSpokenText = null
            mutableUiState.update {
                it.copy(
                    phase = ClientPhase.ReadyToCapture,
                    targetLabel = session.targetLabel,
                    stepNumber = session.stepNumber,
                    instruction = null,
                    confidence = null,
                    message = "会话已恢复，请重新识别当前界面",
                )
            }
        } else if (decision?.status == GuidanceStatus.Completed) {
            val message = decision.instruction ?: "目标已经完成"
            overlay.present(OverlayPresentation.Completed(session.targetPackage, message))
            lastSpokenText = message
            mutableUiState.update {
                it.copy(
                    phase = ClientPhase.Completed,
                    targetLabel = session.targetLabel,
                    stepNumber = session.stepNumber,
                    instruction = message,
                    confidence = decision.confidence,
                )
            }
        } else {
            overlay.present(OverlayPresentation.Ready(session.targetPackage, session.targetLabel))
            mutableUiState.update {
                it.copy(
                    phase = ClientPhase.ReadyToCapture,
                    targetLabel = session.targetLabel,
                    stepNumber = session.stepNumber,
                    instruction = decision?.instruction,
                )
            }
        }
    }

    private fun showRetry(message: String) {
        val session = active ?: return
        lastSpokenText = message
        overlay.present(OverlayPresentation.Retry(session.targetPackage, message))
        speech.speak(message)
        mutableUiState.update {
            it.copy(phase = ClientPhase.Retry, message = message)
        }
    }

    private fun userMessage(error: Exception, fallback: String): String = when (error) {
        is AgentProtocolException -> "服务器响应格式不兼容，请更新应用"
        is AgentHttpException -> when (error.statusCode) {
            404 -> "会话已失效，请重新开始"
            409 -> "当前会话状态已变化，请重新开始"
            422 -> "截图格式校验失败，请重新截图"
            429 -> "当前使用人数较多，请稍后重试"
            else -> fallback
        }

        else -> fallback
    }

    private fun runFailureMessage(snapshot: AgentRunSnapshot): String = when {
        snapshot.status == AgentRunStatus.Cancelled -> "本次识别已取消，可以重新识别"
        snapshot.errorCode == "queue_full" -> "当前使用人数较多，请稍后重试"
        snapshot.errorCode == "agent_timeout" -> "识别超时，请保持页面稳定后重试"
        snapshot.retryable -> "识别服务暂时不可用，请稍后重试"
        else -> "本次识别失败，请重新开始会话"
    }

    private companion object {
        const val MAX_GOAL_LENGTH = 500
        const val SESSION_TTL_SECONDS = 24 * 60 * 60L
        const val RUN_WAIT_TIMEOUT_MILLIS = 100_000L
    }
}
