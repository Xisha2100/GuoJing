package com.xisha.guojing.session

import com.xisha.guojing.data.AgentRepository
import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.guidance.OverlayPresentation
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
import com.xisha.guojing.platform.TargetAppCatalog
import com.xisha.guojing.platform.TargetAppLauncher
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
    fun session_does_not_capture_until_user_requests_guidance() {
        val fixture = Fixture()
        fixture.startSession()

        assertEquals(ClientPhase.ReadyToCapture, fixture.controller.uiState.value.phase)
        assertEquals(0, fixture.capture.captureCount)

        fixture.controller.requestGuidance()
        fixture.scope.advanceUntilIdle()

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
        assertTrue(fixture.overlay.hidden)
        assertEquals(1, fixture.repository.closedSessions)
        assertEquals(null, fixture.store.value)
    }

    @Test
    fun stalled_stream_and_polling_timeout_restore_retry_and_erase_image() {
        val fixture = Fixture()
        fixture.repository.stalled = true
        fixture.startSession()
        fixture.controller.requestGuidance()
        fixture.scope.advanceUntilIdle()

        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertTrue(fixture.overlay.last is OverlayPresentation.Retry)
        assertTrue(fixture.capture.screen.jpegBytes.all { it == 0.toByte() })
    }

    @Test
    fun changed_display_rejects_returned_target_and_clears_run() {
        val fixture = Fixture()
        fixture.capture.displayCurrent = false
        fixture.startSession()
        fixture.controller.requestGuidance()
        fixture.scope.advanceUntilIdle()

        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertEquals(null, fixture.store.value?.currentRunId)
        assertEquals(null, fixture.store.value?.lastDecision)
        assertTrue(fixture.overlay.last is OverlayPresentation.Retry)
    }

    @Test
    fun duplicate_start_click_creates_only_one_session() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        fixture.controller.selectApp("com.tencent.mm")
        fixture.controller.updateGoal("找到扫一扫")
        fixture.controller.setUploadConsent(true)
        fixture.controller.startSession()
        fixture.controller.startSession()
        fixture.scope.advanceUntilIdle()

        assertEquals(1, fixture.repository.createdSessions)
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
    val controller = AgentSessionController(
        repository = repository,
        capture = capture,
        overlay = overlay,
        speech = speech,
        store = store,
        appCatalog = TargetAppCatalog { listOf(TargetApp("com.tencent.mm", "微信")) },
        appLauncher = TargetAppLauncher { true },
        scope = scope,
        nowEpochSeconds = { 1_000L },
    )

    fun startSession() {
        scope.advanceUntilIdle()
        controller.selectApp("com.tencent.mm")
        controller.updateGoal("找到扫一扫")
        controller.setUploadConsent(true)
        controller.startSession()
        scope.advanceUntilIdle()
    }
}

private class FakeRepository : AgentRepository {
    private val sessionId = UUID.fromString("11111111-1111-1111-1111-111111111111")
    private val runId = UUID.fromString("22222222-2222-2222-2222-222222222222")
    var closedSessions = 0
    var createdSessions = 0
    var stalled = false

    override suspend fun createSession(clientSessionId: UUID, goal: String, targetPackage: String): AgentSessionHandle {
        createdSessions += 1
        return AgentSessionHandle(sessionId, "token")
    }

    override suspend fun createRun(
        session: AgentSessionHandle,
        clientTurnId: UUID,
        screenshot: CapturedScreen,
    ) = AgentRunAccepted(runId, AgentRunStatus.Queued, "/api/v1/agent/runs/$runId/events")

    override suspend fun getRun(runId: UUID, accessToken: String) = if (stalled) {
        terminal().copy(status = AgentRunStatus.Running, result = null)
    } else {
        terminal()
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
        status = AgentRunStatus.Completed,
        result = GuidanceDecision(
            GuidanceStatus.Continue,
            "点击右上角加号",
            NormalizedTarget(0.8, 0.02, 0.98, 0.12),
            0.93,
        ),
        errorCode = null,
        retryable = false,
    )
}

private class FakeCapture : ScreenCapturePort {
    override val connected = MutableStateFlow(true)
    val screen = CapturedScreen(byteArrayOf(1, 2, 3), 720, 1280, 1080, 2400, 0)
    var captureCount = 0
    var displayCurrent = true

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
