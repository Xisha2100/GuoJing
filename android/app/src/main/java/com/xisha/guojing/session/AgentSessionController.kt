package com.xisha.guojing.session

import com.xisha.guojing.data.AgentHttpException
import com.xisha.guojing.data.AgentRepository
import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.guidance.OverlayActions
import com.xisha.guojing.guidance.OverlayPresentation
import com.xisha.guojing.model.AgentProtocolException
import com.xisha.guojing.model.AgentRunSnapshot
import com.xisha.guojing.model.AgentRunStatus
import com.xisha.guojing.model.GuidanceDecision
import com.xisha.guojing.model.GuidanceStatus
import com.xisha.guojing.model.TargetApp
import com.xisha.guojing.observation.ScreenCapturePort
import com.xisha.guojing.speech.SpeechPort
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import com.xisha.guojing.model.CaptureGeometry

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
    val selectedPackage: String? = null,
    val goal: String = "",
    val entryEnabled: Boolean = true,
    val accessibilityConnected: Boolean = false,
    val targetLabel: String? = null,
    val stepNumber: Int = 0,
    val instruction: String? = null,
    val confidence: Double? = null,
    val message: String? = null,
    val deviceSetup: DeviceSetupState = DeviceSetupState.Loading,
)

class AgentSessionController(
    private val repository: AgentRepository,
    private val capture: ScreenCapturePort,
    private val overlay: GuidanceOverlayPort,
    private val speech: SpeechPort,
    private val store: ActiveSessionStore,
    private val deviceStore: DeviceAccessStore,
    private val scope: CoroutineScope,
    private val nowEpochSeconds: () -> Long = { Instant.now().epochSecond },
) : OverlayActions, AgentSessionPort {
    private val mutableUiState = MutableStateFlow(AgentClientUiState())
    override val uiState: StateFlow<AgentClientUiState> = mutableUiState.asStateFlow()

    private val recovery = RunRecovery(repository)
    private val confirmedCapture = ConfirmedCapture(capture, repository, recovery)
    private val sessionStorage = Mutex()
    private var confirmedTarget: TargetApp? = null
    private var active: StoredAgentSession? = null
    private var runJob: Job? = null
    private var lastSpokenText: String? = null
    private var entryEnabled = true
    // Serializes local credential work with the synchronous start transition.
    // Initially locked so a save cannot race session restoration.
    private val deviceOperation = Mutex(locked = true)
    private var authorizationBlock: DeviceSetupState.Blocked? = null
    private var sessionGeneration = 0L

    init {
        speech.setRangeListener { start, end -> overlay.showSpeechRange(start, end) }
        scope.launch {
            capture.connected.collect { connected ->
                mutableUiState.update { it.copy(accessibilityConnected = connected) }
            }
        }
        val initialGeneration = sessionGeneration
        scope.launch {
            try {
                initialize(initialGeneration)
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                mutableUiState.update { it.copy(message = "本地会话读取失败，请重新打开应用后重试") }
            } finally {
                deviceOperation.unlock()
            }
        }
    }

    override suspend fun saveInvitation(value: String): InvitationSaveResult {
        if (!deviceOperation.tryLock()) {
            return InvitationSaveResult.Failed("正在处理本地资料，请稍后重试")
        }
        try {
            if (runJob?.isActive == true || active != null || uiState.value.phase != ClientPhase.Setup) {
                return InvitationSaveResult.Failed("请先结束当前指引")
            }
            // Saving an invitation is local; activation requires goal confirmation.
            val existing = deviceStore.load()
            val invited = if (existing?.invitation == value.trim()) existing
                else invitedInstallation(value.trim())
            deviceStore.save(invited)
            currentCoroutineContext().ensureActive()
            authorizationBlock = null
            mutableUiState.update {
                it.copy(deviceSetup = DeviceSetupState.InvitationSaved, message = null)
            }
            return InvitationSaveResult.Saved
        } catch (error: CancellationException) {
            throw error
        } catch (_: IllegalArgumentException) {
            return InvitationSaveResult.Failed("邀请码格式不正确，请检查后重试")
        } catch (_: Exception) {
            return InvitationSaveResult.Failed("邀请码保存失败，请稍后重试")
        } finally {
            deviceOperation.unlock()
        }
    }

    override fun refreshDeviceStatus() {
        if (!deviceOperation.tryLock()) return
        if (runJob?.isActive == true || active != null) {
            deviceOperation.unlock()
            return
        }
        scope.launch {
            try {
                readDeviceSetup()
            } finally {
                deviceOperation.unlock()
            }
        }
    }

    private suspend fun readDeviceSetup() {
        val knownBlock = authorizationBlock
        mutableUiState.update { it.copy(deviceSetup = DeviceSetupState.Loading) }
        try {
            val device = deviceStore.load()
            val setup = when {
                device == null -> DeviceSetupState.MissingInvitation
                knownBlock != null -> knownBlock
                device.deviceId != null -> DeviceSetupState.Activated
                else -> DeviceSetupState.InvitationSaved
            }
            mutableUiState.update { it.copy(deviceSetup = setup) }
        } catch (error: CancellationException) {
            throw error
        } catch (_: Exception) {
            mutableUiState.update {
                it.copy(deviceSetup = DeviceSetupState.Failed("本地设备资料读取失败，请重试"))
            }
        }
    }

    private suspend fun ensureActivated(generation: Long) {
        val access = deviceStore.load() ?: throw AgentHttpException(401, "device_not_activated")
        ensureCurrent(generation)
        if (access.deviceId != null) return
        val activation = repository.activate(access)
        ensureCurrent(generation)
        deviceStore.save(access.copy(deviceId = activation.deviceId, expiresAt = activation.expiresAt, invitation = null))
        ensureCurrent(generation)
        authorizationBlock = null
        mutableUiState.update { it.copy(deviceSetup = DeviceSetupState.Activated) }
    }

    override fun setEntryEnabled(enabled: Boolean) {
        entryEnabled = enabled
        mutableUiState.update { it.copy(entryEnabled = enabled) }
        if (!enabled) {
            endSession()
            speech.stop()
            overlay.hide()
        } else {
            overlay.present(OverlayPresentation.Entry)
        }
    }

    override fun onStartInApp(app: TargetApp, goal: String) {
        if (!deviceOperation.tryLock()) {
            mutableUiState.update { it.copy(message = "正在处理本地资料，请稍后重新开始") }
            return
        }
        try {
            if (!entryEnabled || !capture.connected.value || goal.isBlank() || goal.length > 500) return
            if (mutableUiState.value.phase == ClientPhase.CreatingSession) return
            sessionGeneration += 1
            val generation = sessionGeneration
            confirmedTarget = app
            val previousJob = runJob
            val previous = active
            speech.stop()
            mutableUiState.update { it.copy(phase = ClientPhase.CreatingSession) }
            runJob = scope.launch {
                previousJob?.cancelAndJoin()
                ensureCurrent(generation)
                active = null
                clearStoredSession()
                previous?.let {
                    runCatching {
                        withTimeout(5_000) { repository.closeSession(it.sessionId, it.accessToken) }
                    }
                }
                currentCoroutineContext().ensureActive()
                mutableUiState.update {
                    it.copy(
                        selectedPackage = app.packageName,
                        targetLabel = app.label, goal = goal.trim(),
                    )
                }
                createSession(app, generation)
                if (mutableUiState.value.phase == ClientPhase.ReadyToCapture) captureAndRun(generation)
            }
        } finally {
            deviceOperation.unlock()
        }
    }

    override fun onTargetLeft() {
        speech.stop()
        val session = active ?: return
        if (mutableUiState.value.phase == ClientPhase.ShowingGuidance) {
            mutableUiState.update {
                it.copy(phase = ClientPhase.ReadyToCapture, instruction = null, confidence = null)
            }
            overlay.present(OverlayPresentation.Ready(session.targetPackage, session.targetLabel))
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
        val generation = sessionGeneration
        confirmedTarget = null // A new user step may be in a different window of the same app.
        runJob = scope.launch { captureAndRun(generation) }
    }

    override fun endSession() {
        // An IO-backed startup read may already hold an old session snapshot.
        // Invalidating its generation also covers closing then reopening the entry.
        sessionGeneration += 1
        val session = active
        runJob?.cancel()
        active = null
        confirmedTarget = null
        speech.stop()
        if (entryEnabled) overlay.present(OverlayPresentation.Entry) else overlay.hide()
        lastSpokenText = null
        mutableUiState.update {
            AgentClientUiState(
                entryEnabled = entryEnabled,
                accessibilityConnected = it.accessibilityConnected,
                deviceSetup = it.deviceSetup,
            )
        }
        runJob = scope.launch {
            clearStoredSession()
            session?.currentRunId?.let { runId ->
                runCatching { repository.cancelRun(runId, session.accessToken) }
            }
            session?.let {
                runCatching { repository.closeSession(it.sessionId, it.accessToken) }
            }
        }
    }

    private suspend fun initialize(generation: Long) {
        readDeviceSetup()
        if (generation != sessionGeneration) return
        val restored = store.load() ?: return
        if (generation != sessionGeneration) return
        if (nowEpochSeconds() - restored.createdAtEpochSeconds >= SESSION_TTL_SECONDS) {
            clearStoredSession()
            return
        }
        active = restored
        showRestored(restored)
        if (restored.currentRunId != null) {
            runJob = scope.launch { resumeRun(restored, restored.currentRunId, generation) }
        } else if (restored.pendingTurnId != null) {
            runJob = scope.launch {
                try {
                    val found = recovery.findUploaded(restored, restored.pendingTurnId)
                    ensureCurrent(generation, restored.sessionId)
                    val updated = restored.copy(currentRunId = found.runId)
                    persistSession(updated, generation)
                    resumeRun(updated, found.runId, generation)
                } catch (error: CancellationException) { throw error }
                catch (error: Exception) {
                    ensureCurrent(generation, restored.sessionId)
                    showRetry(userMessage(error, "原任务暂时无法确认，请检查网络后重试"))
                }
            }
        }
    }

    private suspend fun createSession(app: TargetApp, generation: Long) {
        val state = mutableUiState.value
        try {
            ensureActivated(generation)
            ensureCurrent(generation)
            if (!capture.isTargetCurrent(app)) {
                throw IllegalStateException("目标应用已变化，请返回后重新开始")
            }
            val handle = repository.createSession(
                clientSessionId = UUID.randomUUID(),
                goal = state.goal.trim(),
                targetPackage = app.packageName,
            )
            ensureCurrent(generation)
            authorizationBlock = null
            mutableUiState.update { it.copy(deviceSetup = DeviceSetupState.Activated) }
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
            persistSession(session, generation)
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
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            ensureCurrent(generation)
            active = null
            overlay.present(OverlayPresentation.Entry)
            overlay.showMessage(userMessage(error, "创建会话失败，请检查网络后重试"))
            mutableUiState.update {
                it.copy(
                    phase = ClientPhase.Setup,
                    message = userMessage(error, "创建会话失败，请检查网络后重试"),
                )
            }
        }
    }

    private suspend fun captureAndRun(generation: Long) {
        var session = active ?: return
        ensureCurrent(generation, session.sessionId)
        if (session.currentRunId != null || session.pendingTurnId != null) {
            try {
                val found = recovery.findPending(session)
                ensureCurrent(generation, session.sessionId)
                if (found != null) {
                    session = session.copy(currentRunId = found.runId)
                    persistSession(session, generation)
                    resumeRun(session, found.runId, generation)
                    return
                }
                session = SessionReducer.finish(session, null, incrementStep = false)
                persistSession(session, generation)
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                ensureCurrent(generation, session.sessionId)
                showRetry(userMessage(error, "原任务暂时无法确认，请检查网络后重试"))
                return
            }
        }
        speech.stop()
        mutableUiState.update { it.copy(phase = ClientPhase.Capturing, message = null) }
        overlay.present(OverlayPresentation.Loading(session.targetPackage))
        try {
            val target = confirmedTarget ?: TargetApp(session.targetPackage, session.targetLabel)
            val submitted = confirmedCapture.submit(
                session, target,
                ensureCurrent = { ensureCurrent(generation, session.sessionId) },
                persist = { persistSession(it, generation) },
            )
            session = submitted.session
            ensureCurrent(generation, session.sessionId, session.currentRunId)
            mutableUiState.update { it.copy(phase = ClientPhase.WaitingForAgent) }
            val terminal = recovery.awaitTerminal(
                session, submitted.accepted.runId, submitted.accepted.eventsEndpoint,
            )
            ensureCurrent(generation, session.sessionId, session.currentRunId)
            applyTerminal(session, submitted.geometry, terminal, generation)
        } catch (_: TimeoutCancellationException) {
            ensureCurrent(generation, session.sessionId)
            showRetry("等待识别结果超时，请稍后重新识别")
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            ensureCurrent(generation, session.sessionId)
            showRetry(userMessage(error, "识别服务暂时不可用，请稍后重试"))
        }
    }

    private suspend fun applyTerminal(
        session: StoredAgentSession,
        screenshot: CaptureGeometry,
        snapshot: AgentRunSnapshot,
        generation: Long,
    ) {
        ensureCurrent(generation, session.sessionId, snapshot.runId)
        require(snapshot.runId == requireNotNull(session.currentRunId))
        require(snapshot.sessionId == session.sessionId)
        if (snapshot.status != AgentRunStatus.Completed) {
            clearCompletedRun(session, generation = generation)
            showRetry(runFailureMessage(snapshot))
            return
        }
        val decision = snapshot.result ?: throw AgentProtocolException("Missing result")
        when (decision.status) {
            GuidanceStatus.Continue -> {
                if (!targetIsCurrent(session, screenshot) || !capture.isDisplayCurrent(
                        session.targetPackage,
                        screenshot.displayWidth,
                        screenshot.displayHeight,
                        screenshot.rotation,
                    )
                ) {
                    clearCompletedRun(session, generation = generation)
                    showRetry("界面已发生变化，请重新识别")
                    return
                }
                val next = completedStep(session, decision, generation)
                if (!targetIsCurrent(session, screenshot) || !capture.isDisplayCurrent(
                        session.targetPackage, screenshot.displayWidth,
                        screenshot.displayHeight, screenshot.rotation,
                    )
                ) {
                    clearCompletedRun(next, generation = generation)
                    showRetry("界面已发生变化，请重新识别")
                    return
                }
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
                clearCompletedRun(session, decision, generation)
                showRetry(decision.instruction ?: "当前界面无法确定，请保持页面稳定后重试")
            }

            GuidanceStatus.Completed -> {
                val next = completedStep(session, decision, generation)
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
        generation: Long,
    ): StoredAgentSession {
        val next = SessionReducer.finish(session, decision, incrementStep = true)
        persistSession(next, generation)
        return next
    }

    private suspend fun clearCompletedRun(
        session: StoredAgentSession,
        decision: GuidanceDecision? = null,
        generation: Long,
    ) {
        persistSession(SessionReducer.finish(session, decision, incrementStep = false), generation)
    }

    private suspend fun resumeRun(
        session: StoredAgentSession,
        runId: UUID,
        generation: Long,
    ) {
        ensureCurrent(generation, session.sessionId, runId)
        mutableUiState.update { it.copy(phase = ClientPhase.WaitingForAgent) }
        overlay.present(OverlayPresentation.Loading(session.targetPackage))
        try {
            val terminal = recovery.resume(session, runId)
            ensureCurrent(generation, session.sessionId, runId)
            if (terminal.status == AgentRunStatus.Completed && terminal.result != null) {
                val updated = SessionReducer.finish(session, terminal.result, incrementStep = true)
                persistSession(updated, generation)
                showRestored(updated)
            } else {
                clearCompletedRun(session, generation = generation)
                showRetry(runFailureMessage(terminal))
            }
        } catch (_: TimeoutCancellationException) {
            ensureCurrent(generation, session.sessionId)
            showRetry("恢复识别结果超时，请稍后重新识别")
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            ensureCurrent(generation, session.sessionId)
            if (error is AgentHttpException && error.statusCode == 404) {
                clearStoredSession()
                ensureCurrent(generation, session.sessionId)
                active = null
                if (entryEnabled) overlay.present(OverlayPresentation.Entry) else overlay.hide()
                mutableUiState.update {
                    AgentClientUiState(
                        entryEnabled = entryEnabled,
                        accessibilityConnected = it.accessibilityConnected,
                        deviceSetup = it.deviceSetup,
                        message = "原会话已失效，请重新开始",
                    )
                }
            } else {
                showRetry(userMessage(error, "恢复会话失败，请检查网络后重试"))
            }
        }
    }

    private suspend fun ensureCurrent(
        generation: Long,
        sessionId: UUID? = null,
        runId: UUID? = null,
    ) {
        currentCoroutineContext().ensureActive()
        if (!SessionReducer.accepts(generation, sessionGeneration, sessionId, active, runId)) {
            throw CancellationException("Stale session result")
        }
    }

    private suspend fun persistSession(session: StoredAgentSession, generation: Long) {
        sessionStorage.withLock {
            ensureCurrent(generation)
            store.save(session)
            ensureCurrent(generation)
            active = session
        }
    }

    private suspend fun clearStoredSession() {
        sessionStorage.withLock { store.clear() }
    }

    private fun targetIsCurrent(session: StoredAgentSession, geometry: CaptureGeometry) = capture.isTargetCurrent(
        TargetApp(session.targetPackage, session.targetLabel, geometry.windowId),
    )

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

    private fun recordAuthorizationBlock(message: String) {
        val blocked = DeviceSetupState.Blocked(message)
        authorizationBlock = blocked
        mutableUiState.update { it.copy(deviceSetup = blocked) }
    }

    private fun userMessage(error: Exception, fallback: String): String {
        if (error is AgentHttpException) {
            val message = when (error.code) {
                "device_not_activated", "invalid_device_credentials" -> "未开通，请在设置页保存邀请码"
                "device_revoked" -> "设备已停用，请联系邀请人"
                "device_expired" -> "设备授权已到期，请联系邀请人"
                "device_daily_quota_exhausted" -> "设备今日额度已用完，北京时间零点重置"
                "global_daily_quota_exhausted" -> "全站今日额度已用完，北京时间零点重置"
                "service_busy", "queue_full", "service_paused", "service_unavailable" -> "服务繁忙，请稍后重试"
                "invalid_invitation", "invitation_expired", "invitation_already_used" -> "邀请码无效、已使用或已过期，请联系邀请人"
                "device_capacity_reached" -> "试点设备名额已满，请联系邀请人"
                "device_run_in_progress" -> "原任务仍在处理，请稍后重试"
                else -> null
            }
            if (message != null) {
                if (error.code in AUTHORIZATION_ERRORS) {
                    recordAuthorizationBlock(message)
                }
                return message
            }
            return when (error.statusCode) {
                401, 403 -> "设备未获授权，请联系邀请人".also { message ->
                    recordAuthorizationBlock(message)
                }
                404 -> "原会话或任务不存在，请重新开始"
                409 -> "当前任务状态已变化，请稍后重试"
                422 -> "请求校验失败，请更新应用或重新截图"
                429, 503 -> "服务繁忙，请稍后重试"
                else -> fallback
            }
        }
        return when (error) {
            is AgentProtocolException -> "服务器响应格式不兼容，请更新应用"
            is IllegalStateException -> "目标应用已变化或本地保存失败，请返回目标应用后重试"
            else -> fallback
        }
    }

    private fun runFailureMessage(snapshot: AgentRunSnapshot): String {
        val message = when {
            snapshot.status == AgentRunStatus.Cancelled -> "本次识别已取消，可以重新识别"
            snapshot.errorCode == "device_revoked" -> "设备已停用，请联系邀请人"
            snapshot.errorCode == "device_expired" -> "设备授权已到期，请联系邀请人"
            snapshot.errorCode == "device_daily_quota_exhausted" -> "设备今日额度已用完，北京时间零点重置"
            snapshot.errorCode == "global_daily_quota_exhausted" -> "全站今日额度已用完，北京时间零点重置"
            snapshot.errorCode in setOf("queue_full", "queue_timeout", "service_busy", "service_paused") ->
                "当前使用人数较多，请稍后重试"
            snapshot.errorCode == "agent_timeout" -> "识别超时，请保持页面稳定后重试"
            snapshot.retryable -> "识别服务暂时不可用，请稍后重试"
            else -> "本次识别失败，请重新开始会话"
        }
        if (snapshot.errorCode in AUTHORIZATION_ERRORS) {
            recordAuthorizationBlock(message)
        }
        return message
    }

    private companion object {
        val AUTHORIZATION_ERRORS = setOf(
            "device_not_activated", "invalid_device_credentials", "device_revoked", "device_expired",
            "invalid_invitation", "invitation_expired", "invitation_already_used",
        )
        const val MAX_GOAL_LENGTH = 500
        const val SESSION_TTL_SECONDS = 24 * 60 * 60L
    }
}
