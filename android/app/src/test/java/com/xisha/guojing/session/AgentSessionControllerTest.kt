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
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runCurrent
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
    fun page_change_while_saving_result_rejects_guidance_and_replay() {
        val fixture = Fixture()
        val gate = CompletableDeferred<Unit>()
        fixture.store.terminalSaveGate = gate
        fixture.scope.advanceUntilIdle()
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        fixture.scope.runCurrent()
        assertTrue(fixture.store.terminalSaveStarted)
        fixture.controller.onTargetLeft()
        gate.complete(Unit)
        fixture.scope.advanceUntilIdle()
        fixture.controller.onReplay()
        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertTrue(!fixture.speech.spoken.contains("点击右上角加号"))
    }

    @Test
    fun invalidated_visible_guidance_cannot_be_replayed_or_restored_by_rotation_back() {
        val fixture = Fixture()
        fixture.startSession()
        fixture.capture.displayCurrent = false
        fixture.controller.onTargetLeft()
        fixture.capture.displayCurrent = true
        val speechCount = fixture.speech.spoken.size
        fixture.controller.onReplay()
        assertEquals(speechCount, fixture.speech.spoken.size)
        assertEquals(ClientPhase.ReadyToCapture, fixture.controller.uiState.value.phase)
        assertTrue(fixture.overlay.last is OverlayPresentation.Ready)
        assertEquals(1, fixture.capture.captureCount)
    }

    @Test
    fun clear_failure_blocks_new_capture_and_does_not_prevent_remote_close() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        fixture.store.failClear = true
        fixture.startSession()
        assertEquals(ClientPhase.Setup, fixture.controller.uiState.value.phase)
        assertEquals(0, fixture.capture.captureCount)
        fixture.store.failClear = false
        fixture.startSession()
        fixture.store.failClear = true
        fixture.controller.endSession()
        fixture.scope.advanceUntilIdle()
        assertEquals(1, fixture.repository.closedSessions)
        assertTrue(fixture.controller.uiState.value.message!!.contains("清除失败"))
    }

    @Test
    fun page_change_during_analysis_rejects_late_guidance() {
        val fixture = Fixture()
        fixture.repository.onUpload = { fixture.controller.onTargetLeft() }
        fixture.startSession()
        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertTrue(fixture.overlay.last is OverlayPresentation.Retry)
        assertTrue(!fixture.speech.spoken.contains("点击右上角加号"))
        assertEquals(1, fixture.capture.captureCount)
    }

    @Test
    fun invitation_save_and_initialization_do_not_activate_or_capture() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        assertEquals(InvitationSaveResult.Saved, fixture.saveInvitation("c".repeat(43)))
        fixture.scope.advanceUntilIdle()
        assertEquals(0, fixture.repository.activations)
        assertEquals(0, fixture.capture.captureCount)
        assertEquals("c".repeat(43), fixture.deviceStore.value?.invitation)
    }

    @Test
    fun local_device_state_distinguishes_loading_missing_saved_and_activated() {
        val fixture = Fixture()
        assertEquals(DeviceSetupState.Loading, fixture.controller.uiState.value.deviceSetup)
        fixture.deviceStore.value = null
        fixture.scope.advanceUntilIdle()
        assertEquals(DeviceSetupState.MissingInvitation, fixture.controller.uiState.value.deviceSetup)
        assertEquals(InvitationSaveResult.Saved, fixture.saveInvitation("c".repeat(43)))
        assertEquals(DeviceSetupState.InvitationSaved, fixture.controller.uiState.value.deviceSetup)
        fixture.deviceStore.value = fixture.deviceStore.value?.copy(deviceId = UUID.randomUUID())
        fixture.controller.refreshDeviceStatus()
        fixture.scope.advanceUntilIdle()
        assertEquals(DeviceSetupState.Activated, fixture.controller.uiState.value.deviceSetup)
        assertEquals(0, fixture.repository.activations)
        assertEquals(0, fixture.capture.captureCount)
    }

    @Test
    fun initialization_and_restoration_reject_invitation_changes_until_finished() {
        val fixture = Fixture()
        val result = runBlocking { fixture.controller.saveInvitation("c".repeat(43)) }
        assertTrue(result is InvitationSaveResult.Failed)
        assertEquals(0, fixture.deviceStore.saves)
        fixture.scope.advanceUntilIdle()
        assertEquals(InvitationSaveResult.Saved, fixture.saveInvitation("c".repeat(43)))
    }

    @Test
    fun restoring_a_session_blocks_save_before_and_after_local_restore() {
        val fixture = Fixture()
        val gate = CompletableDeferred<Unit>()
        fixture.store.loadGate = gate
        fixture.store.value = StoredAgentSession(
            sessionId = UUID.randomUUID(), accessToken = "token", goal = "找到扫一扫",
            targetPackage = "com.tencent.mm", targetLabel = "微信", createdAtEpochSeconds = 1_000L,
            stepNumber = 0, currentRunId = null, eventsEndpoint = null, lastDecision = null,
            displayWidth = null, displayHeight = null, rotation = null,
        )
        fixture.scope.runCurrent()
        assertTrue(fixture.saveInvitation("c".repeat(43)) is InvitationSaveResult.Failed)
        gate.complete(Unit)
        fixture.scope.advanceUntilIdle()
        assertEquals(ClientPhase.ReadyToCapture, fixture.controller.uiState.value.phase)
        assertTrue(fixture.saveInvitation("c".repeat(43)) is InvitationSaveResult.Failed)
        assertEquals(0, fixture.deviceStore.saves)
        assertEquals(0, fixture.capture.captureCount)
        assertEquals(0, fixture.repository.activations)
    }

    @Test
    fun disabling_entry_discards_startup_snapshot_even_when_entry_is_reopened() {
        for (reopen in listOf(false, true)) {
            for (pendingTurn in listOf(false, true)) {
                val fixture = Fixture()
                val gate = CompletableDeferred<Unit>()
                fixture.store.loadGate = gate
                fixture.store.value = StoredAgentSession(
                    sessionId = UUID.fromString("11111111-1111-1111-1111-111111111111"),
                    accessToken = "token", goal = "找到扫一扫", targetPackage = "com.tencent.mm",
                    targetLabel = "微信", createdAtEpochSeconds = 1_000L, stepNumber = 0,
                    currentRunId = if (pendingTurn) null else
                        UUID.fromString("22222222-2222-2222-2222-222222222222"),
                    eventsEndpoint = null, lastDecision = null, displayWidth = null,
                    displayHeight = null, rotation = null,
                    pendingTurnId = if (pendingTurn) UUID.randomUUID() else null,
                )
                fixture.scope.runCurrent()
                assertEquals(1, fixture.store.loads)
                fixture.controller.setEntryEnabled(false)
                if (reopen) fixture.controller.setEntryEnabled(true)
                fixture.scope.runCurrent()
                assertEquals(null, fixture.store.value)

                // The stale snapshot returns after cancellation and optional reopening.
                gate.complete(Unit)
                fixture.scope.advanceUntilIdle()

                assertEquals(ClientPhase.Setup, fixture.controller.uiState.value.phase)
                assertEquals(reopen, fixture.controller.uiState.value.entryEnabled)
                assertEquals(!reopen, fixture.overlay.hidden)
                if (reopen) assertEquals(OverlayPresentation.Entry, fixture.overlay.last)
                assertEquals(0, fixture.repository.runLookups)
                assertEquals(0, fixture.repository.lookups)
                assertEquals(0, fixture.repository.activations)
                assertEquals(0, fixture.capture.captureCount)
                assertEquals(null, fixture.store.value)
            }
        }
    }

    @Test
    fun invitation_failure_keeps_existing_credentials_and_ready_state() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        val existing = fixture.deviceStore.value
        assertTrue(fixture.saveInvitation("bad") is InvitationSaveResult.Failed)
        fixture.deviceStore.saveFailure = java.io.IOException("disk failure")
        assertTrue(fixture.saveInvitation("c".repeat(43)) is InvitationSaveResult.Failed)
        assertEquals(existing, fixture.deviceStore.value)
        assertEquals(DeviceSetupState.InvitationSaved, fixture.controller.uiState.value.deviceSetup)
        assertEquals(null, fixture.controller.uiState.value.message)
        assertEquals(0, fixture.repository.activations)
    }

    @Test
    fun pending_save_rejects_duplicate_and_session_start_without_activating() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        val gate = CompletableDeferred<Unit>()
        fixture.deviceStore.saveGate = gate
        val first = fixture.scope.async { fixture.controller.saveInvitation("c".repeat(43)) }
        fixture.scope.runCurrent()
        val second = fixture.scope.async { fixture.controller.saveInvitation("d".repeat(43)) }
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        fixture.scope.runCurrent()
        assertTrue(runBlocking { second.await() } is InvitationSaveResult.Failed)
        assertEquals(1, fixture.deviceStore.saves)
        assertEquals(0, fixture.repository.activations)
        assertEquals(0, fixture.repository.createdSessions)
        assertEquals(0, fixture.capture.captureCount)
        gate.complete(Unit)
        fixture.scope.advanceUntilIdle()
        assertEquals(InvitationSaveResult.Saved, runBlocking { first.await() })
        assertEquals("c".repeat(43), fixture.deviceStore.value?.invitation)
    }

    @Test
    fun cancelled_save_propagates_cancellation_and_releases_local_operation() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        fixture.deviceStore.saveGate = CompletableDeferred()
        val first = fixture.scope.async { fixture.controller.saveInvitation("c".repeat(43)) }
        fixture.scope.runCurrent()
        first.cancel()
        fixture.scope.runCurrent()
        assertTrue(first.isCancelled)
        assertEquals("b".repeat(43), fixture.deviceStore.value?.invitation)
        fixture.deviceStore.saveGate = null
        assertEquals(InvitationSaveResult.Saved, fixture.saveInvitation("d".repeat(43)))
    }

    @Test
    fun current_session_rejects_credential_changes() {
        val fixture = Fixture()
        fixture.startSession()
        val existing = fixture.deviceStore.value
        assertEquals(
            InvitationSaveResult.Failed("请先结束当前指引"),
            fixture.saveInvitation("c".repeat(43)),
        )
        assertEquals(existing, fixture.deviceStore.value)
    }

    @Test
    fun local_read_failure_can_be_retried_without_network_or_capture() {
        val fixture = Fixture()
        fixture.deviceStore.loadFailure = java.io.IOException("read failure")
        fixture.scope.advanceUntilIdle()
        assertTrue(fixture.controller.uiState.value.deviceSetup is DeviceSetupState.Failed)
        fixture.deviceStore.loadFailure = null
        fixture.controller.refreshDeviceStatus()
        fixture.scope.advanceUntilIdle()
        assertEquals(DeviceSetupState.InvitationSaved, fixture.controller.uiState.value.deviceSetup)
        assertEquals(0, fixture.repository.activations)
        assertEquals(0, fixture.repository.createdSessions)
        assertEquals(0, fixture.capture.captureCount)
    }

    @Test
    fun transient_server_error_does_not_replace_activated_state() {
        for (code in listOf("service_busy", "device_daily_quota_exhausted")) {
            val fixture = Fixture()
            fixture.repository.creationFailure = AgentHttpException(503, code)
            fixture.startSession()
            assertEquals(DeviceSetupState.Activated, fixture.controller.uiState.value.deviceSetup)
            assertTrue(fixture.controller.uiState.value.message != null)
            assertEquals(0, fixture.capture.captureCount)
        }
    }

    @Test
    fun server_revocation_remains_blocked_after_end_and_local_refresh() {
        val fixture = Fixture()
        fixture.repository.terminalFailureCode = "device_revoked"
        fixture.startSession()
        val blocked = DeviceSetupState.Blocked("设备已停用，请联系邀请人")
        assertEquals(blocked, fixture.controller.uiState.value.deviceSetup)
        fixture.controller.endSession()
        fixture.scope.advanceUntilIdle()
        fixture.controller.refreshDeviceStatus()
        fixture.scope.advanceUntilIdle()
        assertEquals(blocked, fixture.controller.uiState.value.deviceSetup)
        fixture.deviceStore.loadFailure = java.io.IOException("read failed")
        fixture.controller.refreshDeviceStatus()
        fixture.scope.advanceUntilIdle()
        assertTrue(fixture.controller.uiState.value.deviceSetup is DeviceSetupState.Failed)
        fixture.deviceStore.loadFailure = null
        fixture.controller.refreshDeviceStatus()
        fixture.scope.advanceUntilIdle()
        assertEquals(blocked, fixture.controller.uiState.value.deviceSetup)
        assertEquals(InvitationSaveResult.Saved, fixture.saveInvitation("c".repeat(43)))
        assertEquals(DeviceSetupState.InvitationSaved, fixture.controller.uiState.value.deviceSetup)
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
    fun retry_recovers_a_found_turn_without_cancelling_or_recapturing() {
        val fixture = Fixture()
        fixture.repository.loseUploadResponse = true
        fixture.repository.turnLookupFailure = java.io.IOException("offline")
        fixture.startSession()
        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertTrue(fixture.store.value?.pendingTurnId != null)

        fixture.repository.turnLookupFailure = null
        fixture.controller.onPrimaryAction()
        fixture.scope.advanceUntilIdle()

        assertEquals(1, fixture.repository.uploads)
        assertEquals(1, fixture.capture.captureCount)
        assertEquals(0, fixture.repository.cancelledRuns)
        assertEquals(ClientPhase.ReadyToCapture, fixture.controller.uiState.value.phase)
        assertEquals(null, fixture.store.value?.pendingTurnId)
        assertTrue(fixture.overlay.last is OverlayPresentation.Ready)
    }

    @Test
    fun retry_after_timeout_reads_original_result_without_new_capture() {
        val fixture = Fixture()
        fixture.repository.stalled = true
        fixture.startSession()
        fixture.repository.stalled = false
        fixture.controller.onPrimaryAction()
        fixture.scope.advanceUntilIdle()

        assertEquals(1, fixture.repository.uploads)
        assertEquals(1, fixture.capture.captureCount)
        assertEquals(0, fixture.repository.cancelledRuns)
        assertEquals(ClientPhase.ReadyToCapture, fixture.controller.uiState.value.phase)
    }

    @Test
    fun ending_during_a_late_store_write_clears_it_without_showing_or_speaking() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        val gate = CompletableDeferred<Unit>()
        fixture.store.terminalSaveGate = gate
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        fixture.scope.runCurrent()
        assertTrue(fixture.store.terminalSaveStarted)
        fixture.controller.endSession()
        fixture.scope.runCurrent()
        gate.complete(Unit)
        fixture.scope.advanceUntilIdle()

        assertEquals(null, fixture.store.value)
        assertEquals(ClientPhase.Setup, fixture.controller.uiState.value.phase)
        assertEquals(OverlayPresentation.Entry, fixture.overlay.last)
        assertTrue(fixture.speech.spoken.isEmpty())
    }

    @Test
    fun wrong_session_stream_is_rejected_without_polling_or_displaying() {
        val fixture = Fixture()
        fixture.repository.wrongIdentity = true
        fixture.startSession()
        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertEquals("服务器响应格式不兼容，请更新应用", fixture.controller.uiState.value.message)
        assertEquals(0, fixture.repository.runLookups)
        assertTrue(fixture.overlay.last is OverlayPresentation.Retry)
    }

    @Test
    fun changed_window_in_same_app_rejects_returned_coordinates() {
        val fixture = Fixture()
        fixture.repository.onUpload = { fixture.capture.currentWindowId = 8 }
        fixture.startSession()
        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertEquals(null, fixture.store.value?.lastDecision)
        assertEquals(1, fixture.capture.captureCount)
        assertTrue(fixture.overlay.last is OverlayPresentation.Retry)
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
    fun changed_window_during_pending_turn_save_blocks_upload_and_erases_image() {
        val fixture = Fixture()
        fixture.scope.advanceUntilIdle()
        val gate = CompletableDeferred<Unit>()
        fixture.store.pendingSaveGate = gate
        fixture.controller.onStartInApp(TargetApp("com.tencent.mm", "微信"), "找到扫一扫")
        fixture.scope.runCurrent()
        assertEquals(1, fixture.capture.captureCount)
        fixture.capture.currentWindowId = 8
        gate.complete(Unit)
        fixture.scope.advanceUntilIdle()

        assertEquals(0, fixture.repository.uploads)
        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertTrue(fixture.capture.screen.jpegBytes.all { it == 0.toByte() })
    }

    @Test
    fun missing_restored_run_with_clear_failure_remains_recoverable() {
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
        fixture.store.failClear = true
        fixture.repository.runLookupFailure = AgentHttpException(404, "run_not_found")
        fixture.scope.advanceUntilIdle()

        assertTrue(fixture.store.value != null)
        assertEquals(ClientPhase.Retry, fixture.controller.uiState.value.phase)
        assertTrue(fixture.controller.uiState.value.message!!.contains("清除失败"))
        assertEquals(0, fixture.capture.captureCount)
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

    fun saveInvitation(value: String): InvitationSaveResult {
        val result = scope.async { controller.saveInvitation(value) }
        scope.advanceUntilIdle()
        return runBlocking { result.await() }
    }

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
    var runLookups = 0
    var cancelledRuns = 0
    var wrongIdentity = false
    var turnLookupFailure: Exception? = null
    var onUpload: () -> Unit = {}
    var loseUploadResponse = false
    var runLookupFailure: AgentHttpException? = null
    var terminalFailureCode: String? = null
    var activationFailure: String? = null
    var creationFailure: AgentHttpException? = null
    var onActivation: () -> Unit = {}
    override suspend fun activate(access: DeviceAccess): DeviceActivation {
        activations += 1
        onActivation()
        activationFailure?.let { throw AgentHttpException(403, it) }
        return DeviceActivation(UUID.randomUUID(), "2027-01-01T00:00:00Z")
    }
    override suspend fun getTurn(session: AgentSessionHandle, clientTurnId: UUID): AgentRunSnapshot {
        lookups += 1
        turnLookupFailure?.let { throw it }
        return terminal()
    }

    override suspend fun createSession(clientSessionId: UUID, goal: String, targetPackage: String): AgentSessionHandle {
        creationFailure?.let { throw it }
        createdSessions += 1
        return AgentSessionHandle(sessionId, "token")
    }

    override suspend fun createRun(
        session: AgentSessionHandle,
        clientTurnId: UUID,
        screenshot: CapturedScreen,
    ): AgentRunAccepted {
        uploads += 1
        onUpload()
        if (loseUploadResponse) throw java.io.IOException("response lost")
        return AgentRunAccepted(runId, AgentRunStatus.Queued, "/api/v1/agent/runs/$runId/events")
    }

    override suspend fun getRun(runId: UUID, accessToken: String): AgentRunSnapshot {
        runLookups += 1
        runLookupFailure?.let { throw it }
        return if (stalled) {
            terminal().copy(status = AgentRunStatus.Running, result = null)
        } else {
            terminal()
        }
    }

    override fun observeRun(eventsEndpoint: String, accessToken: String): Flow<AgentRunSnapshot> =
        if (stalled) flow { awaitCancellation() } else flowOf(terminal())

    override suspend fun cancelRun(runId: UUID, accessToken: String) { cancelledRuns += 1 }

    override suspend fun closeSession(sessionId: UUID, accessToken: String) {
        closedSessions += 1
    }

    private fun terminal() = AgentRunSnapshot(
        runId = runId,
        sessionId = if (wrongIdentity) UUID.randomUUID() else sessionId,
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
    val screen = CapturedScreen(byteArrayOf(1, 2, 3), 720, 1280, 1080, 2400, 0, windowId = 7)
    var captureCount = 0
    var displayCurrent = true
    var targetCurrent = true
    var currentWindowId = 7
    override fun isTargetCurrent(app: TargetApp) = targetCurrent &&
        (app.windowId == null || app.windowId == currentWindowId)

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
    var failClear = false
    var value: StoredAgentSession? = null
    var loadGate: CompletableDeferred<Unit>? = null
    var loads = 0
    var terminalSaveGate: CompletableDeferred<Unit>? = null
    var terminalSaveStarted = false
    var pendingSaveGate: CompletableDeferred<Unit>? = null
    override suspend fun load(): StoredAgentSession? {
        loads += 1
        val snapshot = value
        loadGate?.await()
        return snapshot
    }
    override suspend fun save(value: StoredAgentSession) {
        if (value.pendingTurnId != null && value.currentRunId == null) pendingSaveGate?.await()
        if (value.lastDecision != null) {
            terminalSaveStarted = true
            withContext(NonCancellable) { terminalSaveGate?.await() }
        }
        this.value = value
    }
    override suspend fun clear() { check(!failClear); value = null }
}

private class FakeDeviceStore : DeviceAccessStore {
    var value: DeviceAccess? = DeviceAccess(UUID.randomUUID(), "a".repeat(43), "b".repeat(43))
    var saves = 0
    var loadFailure: Exception? = null
    var saveFailure: Exception? = null
    var saveGate: CompletableDeferred<Unit>? = null
    override suspend fun load(): DeviceAccess? {
        loadFailure?.let { throw it }
        return value
    }
    override suspend fun save(value: DeviceAccess) {
        saves += 1
        saveGate?.await()
        saveFailure?.let { throw it }
        this.value = value
    }
}
