package com.xisha.guojing.session

import com.xisha.guojing.data.AgentRepository
import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.guidance.OverlayPresentation
import com.xisha.guojing.model.DeviceAccess
import com.xisha.guojing.model.DeviceActivation
import com.xisha.guojing.data.AgentHttpException
import com.xisha.guojing.model.AgentRunAccepted
import com.xisha.guojing.model.AgentRunSnapshot
import com.xisha.guojing.model.AgentRunStatus
import com.xisha.guojing.model.AgentSessionHandle
import com.xisha.guojing.model.CapturedScreen
import com.xisha.guojing.model.GuidanceDecision
import com.xisha.guojing.model.GuidanceStatus
import com.xisha.guojing.model.NormalizedTarget
import com.xisha.guojing.model.TargetApp
import com.xisha.guojing.observation.ScreenCapturePort
import com.xisha.guojing.speech.SpeechPort
import java.util.UUID
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AgentSessionControllerTest {
    @Test
    fun invitation_save_and_initialization_do_not_activate_or_capture() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        fixture.controller.saveInvitation("c".repeat(43))
        fixture.scope.advanceUntilIdle()
        assertEquals(0, fixture.repository.activations)
        assertEquals(0, fixture.capture.captureCount)
        assertEquals("c".repeat(43), fixture.deviceStore.value?.invitation)
    }

    @Test
    fun activation_revalidates_target_before_capture_or_session_creation() {
        val fixture = Fixture()
        fixture.repository.onActivation = { fixture.capture.targetCurrent = false }
        fixture.startSession()
        assertEquals(1, fixture.repository.activations)
        assertEquals(0, fixture.repository.createdSessions)
        assertEquals(0, fixture.capture.captureCount)
    }

    @Test
    fun missing_invitation_and_revocation_block_capture() {
        for (code in listOf("device_revoked", "device_expired", "device_daily_quota_exhausted", "global_daily_quota_exhausted")) {
            val fixture = Fixture()
            fixture.repository.activationFailure = code
            fixture.startSession()
            assertEquals(0, fixture.capture.captureCount)
            assertEquals(0, fixture.repository.uploads)
            assertTrue(fixture.controller.uiState.value.message != null)
        }
        val fixture = Fixture()
        fixture.deviceStore.value = null
        fixture.startSession()
        assertEquals(0, fixture.repository.activations)
        assertEquals(0, fixture.capture.captureCount)
    }

    @Test
    fun lost_upload_response_looks_up_original_without_recapture_or_reupload() {
        val fixture = Fixture()
        fixture.repository.loseUploadResponse = true
        fixture.startSession()
        assertEquals(1, fixture.capture.captureCount)
        assertEquals(1, fixture.repository.uploads)
        assertEquals(1, fixture.repository.lookups)
        assertEquals(ClientPhase.ShowingGuidance, fixture.controller.uiState.value.phase)
        assertEquals(null, fixture.store.value?.pendingTurnId)
    }

    @Test
    fun failed_run_shows_specific_quota_message_without_another_upload() {
        val fixture = Fixture()
        fixture.repository.terminalFailureCode = "global_daily_quota_exhausted"
        fixture.startSession()

        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertEquals("全站今日额度已用完，北京时间零点重置", fixture.controller.uiState.value.message)
        assertEquals(1, fixture.repository.uploads)
        assertEquals(1, fixture.capture.captureCount)
    }

    @Test
    fun missing_restored_run_clears_session_and_restores_floating_entry() {
        val fixture = Fixture()
        fixture.store.value = StoredAgentSession(
            sessionId = UUID.fromString("11111111-1111-1111-1111-111111111111"),
            accessToken = "token",
            goal = "找到扫一扫",
            targetPackage = "com.tencent.mm",
            targetLabel = "微信",
            createdAtEpochSeconds = 1_000L,
            stepNumber = 0,
            currentRunId = UUID.fromString("22222222-2222-2222-2222-222222222222"),
            eventsEndpoint = null,
            lastDecision = null,
            displayWidth = null,
            displayHeight = null,
            rotation = null,
        )
        fixture.repository.runLookupFailure = AgentHttpException(404, "run_not_found")
        fixture.scope.advanceUntilIdle()

        assertEquals(null, fixture.store.value)
        assertEquals(ClientPhase.Setup, fixture.controller.uiState.value.phase)
        assertEquals("原会话已失效，请重新开始", fixture.controller.uiState.value.message)
        assertEquals(OverlayPresentation.Entry, fixture.overlay.last)
        assertEquals(false, fixture.overlay.hidden)
        assertEquals(0, fixture.capture.captureCount)
    }

    @Test
    fun stream_and_polling_share_150_second_budget() {
        val fixture = Fixture()
        fixture.repository.stalled = true
        fixture.startSession()
        assertEquals(150_000L, fixture.scope.testScheduler.currentTime)
    }

    @Test
    fun confirmed_goal_starts_current_app_and_captures_once() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        assertEquals(0, fixture.capture.captureCount)
        assertEquals(0, fixture.repository.createdSessions)
        fixture.startSession()

        assertEquals(1, fixture.capture.captureCount)
        assertEquals(ClientPhase.ShowingGuidance, fixture.controller.uiState.value.phase)
        assertTrue(fixture.capture.screen.jpegBytes.all { it == 0.toByte() })
        assertTrue(fixture.overlay.last is OverlayPresentation.Guidance)
        assertEquals(listOf("点击右上角加号"), fixture.speech.spoken)
    }

    @Test
    fun ending_session_removes_overlay_and_remote_session() {
        val fixture = Fixture()
        fixture.startSession()

        fixture.controller.endSession()
        fixture.scope.advanceUntilIdle()

        assertEquals(ClientPhase.Setup, fixture.controller.uiState.value.phase)
        assertEquals(OverlayPresentation.Entry, fixture.overlay.last)
        assertEquals(1, fixture.repository.closedSessions)
        assertEquals(null, fixture.store.value)
    }

    @Test
    fun stalled_stream_and_polling_timeout_restore_retry_and_erase_image() {
        val fixture = Fixture()
        fixture.repository.stalled = true
        fixture.startSession()

        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertTrue(fixture.overlay.last is OverlayPresentation.Retry)
        assertTrue(fixture.capture.screen.jpegBytes.all { it == 0.toByte() })
    }

    @Test
    fun changed_display_rejects_returned_target_and_clears_run() {
        val fixture = Fixture()
        fixture.capture.displayCurrent = false
        fixture.startSession()

        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertEquals(null, fixture.store.value?.currentRunId)
        assertEquals(null, fixture.store.value?.lastDecision)
        assertTrue(fixture.overlay.last is OverlayPresentation.Retry)
    }

    @Test
    fun duplicate_start_click_creates_only_one_session() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        fixture.scope.advanceUntilIdle()

        assertEquals(1, fixture.repository.createdSessions)
    }

    @Test
    fun leaving_app_discards_visible_coordinates_but_keeps_session() {
        val fixture = Fixture()
        fixture.startSession()
        fixture.controller.onTargetLeft()
        assertEquals(ClientPhase.ReadyToCapture, fixture.controller.uiState.value.phase)
        assertEquals(null, fixture.controller.uiState.value.instruction)
        assertEquals(0, fixture.repository.closedSessions)
    }

    @Test
    fun starting_in_another_app_closes_old_session() {
        val fixture = Fixture()
        fixture.startSession()
        fixture.controller.onStartInApp(TargetApp("com.android.settings", "设置"), "找到蓝牙")
        fixture.scope.advanceUntilIdle()
        assertEquals(2, fixture.repository.createdSessions)
        assertEquals(1, fixture.repository.closedSessions)
        assertEquals("com.android.settings", fixture.store.value?.targetPackage)
    }

    @Test
    fun empty_goal_does_not_create_or_capture() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), " ")
        fixture.scope.advanceUntilIdle()
        assertEquals(0, fixture.repository.createdSessions)
        assertEquals(0, fixture.capture.captureCount)
    }

    @Test
    fun disabling_entry_cancels_pending_creation_without_restoring_overlay() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        fixture.controller.setEntryEnabled(false)
        fixture.scope.advanceUntilIdle()
        assertEquals(0, fixture.repository.createdSessions)
        assertEquals(ClientPhase.Setup, fixture.controller.uiState.value.phase)
        assertTrue(fixture.overlay.hidden)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
private class Fixture {
    val dispatcher = StandardTestDispatcher()
    val scope = TestScope(dispatcher)
    val repository = FakeRepository()
    val capture = FakeCapture()
    val overlay = FakeOverlay()
    val speech = FakeSpeech()
    val store = FakeStore()
    val deviceStore = FakeDeviceStore()
    val controller = AgentSessionController(
        repository = repository,
        capture = capture,
        overlay = overlay,
        speech = speech,
        store = store,
        deviceStore = deviceStore,
        scope = scope,
        nowEpochSeconds = { 1_000L },
    )

    fun startSession() {
        scope.advanceUntilIdle()
        controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        scope.advanceUntilIdle()
    }
}

private class FakeRepository : AgentRepository {
    private val sessionId = UUID.fromString("11111111-1111-1111-1111-111111111111")
    private val runId = UUID.fromString("22222222-2222-2222-2222-222222222222")
    var closedSessions = 0
    var createdSessions = 0
    var stalled = false
    var activations = 0
    var uploads = 0
    var lookups = 0
    var loseUploadResponse = false
    var runLookupFailure: AgentHttpException? = null
    var terminalFailureCode: String? = null
    var activationFailure: String? = null
    var onActivation: () -> Unit = {}
    override suspend fun activate(access: DeviceAccess): DeviceActivation {
        activations += 1
        onActivation()
        activationFailure?.let { throw AgentHttpException(403, it) }
        return DeviceActivation(UUID.randomUUID(), "2027-01-01T00:00:00Z")
    }
    override suspend fun getTurn(session: AgentSessionHandle, clientTurnId: UUID): AgentRunSnapshot {
        lookups += 1
        return terminal()
    }

    override suspend fun createSession(clientSessionId: UUID, goal: String, targetPackage: String): AgentSessionHandle {
        createdSessions += 1
        return AgentSessionHandle(sessionId, "token")
    }

    override suspend fun createRun(
        session: AgentSessionHandle,
        clientTurnId: UUID,
        screenshot: CapturedScreen,
    ): AgentRunAccepted {
        uploads += 1
        if (loseUploadResponse) throw java.io.IOException("response lost")
        return AgentRunAccepted(runId, AgentRunStatus.Queued, "/api/v1/agent/runs/$runId/events")
    }

    override suspend fun getRun(runId: UUID, accessToken: String): AgentRunSnapshot {
        runLookupFailure?.let { throw it }
        return if (stalled) {
            terminal().copy(status = AgentRunStatus.Running, result = null)
        } else {
            terminal()
        }
    }

    override fun observeRun(eventsEndpoint: String, accessToken: String): Flow<AgentRunSnapshot> =
        if (stalled) flow { awaitCancellation() } else flowOf(terminal())

    override suspend fun cancelRun(runId: UUID, accessToken: String) = Unit

    override suspend fun closeSession(sessionId: UUID, accessToken: String) {
        closedSessions += 1
    }

    private fun terminal() = AgentRunSnapshot(
        runId = runId,
        sessionId = sessionId,
        status = if (terminalFailureCode == null) AgentRunStatus.Completed else AgentRunStatus.Failed,
        result = if (terminalFailureCode == null) GuidanceDecision(
            GuidanceStatus.Continue,
            "点击右上角加号",
            NormalizedTarget(0.8, 0.02, 0.98, 0.12),
            0.93,
        ) else null,
        errorCode = terminalFailureCode,
        retryable = false,
    )
}

private class FakeCapture : ScreenCapturePort {
    override val connected = MutableStateFlow(true)
    val screen = CapturedScreen(byteArrayOf(1, 2, 3), 720, 1280, 1080, 2400, 0)
    var captureCount = 0
    var displayCurrent = true
    var targetCurrent = true
    override fun isTargetCurrent(app: TargetApp) = targetCurrent

    override suspend fun capture(targetPackage: String): CapturedScreen {
        captureCount += 1
        return screen
    }

    override fun isDisplayCurrent(
        targetPackage: String,
        displayWidth: Int,
        displayHeight: Int,
        rotation: Int,
    ) = displayCurrent
}

private class FakeOverlay : GuidanceOverlayPort {
    var last: OverlayPresentation? = null
    var hidden = false

    override fun present(value: OverlayPresentation) {
        last = value
        hidden = false
    }

    override fun hide() {
        hidden = true
    }
}

private class FakeSpeech : SpeechPort {
    val spoken = mutableListOf<String>()
    override fun speak(text: String) { spoken += text }
    override fun stop() = Unit
    override fun close() = Unit
}

private class FakeStore : ActiveSessionStore {
    var value: StoredAgentSession? = null
    override suspend fun load() = value
    override suspend fun save(value: StoredAgentSession) { this.value = value }
    override suspend fun clear() { value = null }
}

private class FakeDeviceStore : DeviceAccessStore {
    var value: DeviceAccess? = DeviceAccess(UUID.randomUUID(), "a".repeat(43), "b".repeat(43))
    override suspend fun load() = value
    override suspend fun save(value: DeviceAccess) { this.value = value }
}
