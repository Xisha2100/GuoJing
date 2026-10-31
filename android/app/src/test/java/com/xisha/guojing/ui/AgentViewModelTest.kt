package com.xisha.guojing.ui

import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.AgentSessionPort
import com.xisha.guojing.session.ClientPhase
import com.xisha.guojing.session.DeviceSetupState
import com.xisha.guojing.session.InvitationSaveResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AgentViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val stores = mutableListOf<ViewModelStore>()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        stores.forEach(ViewModelStore::clear)
        Dispatchers.resetMain()
    }

    @Test
    fun failed_save_preserves_draft_and_expanded_form_for_retry() = runTest(dispatcher) {
        val port = FakeSessionPort()
        port.save = { InvitationSaveResult.Failed("本机保存失败") }
        val model = model(port)
        model.setInvitationExpanded(true)
        model.setInvitationDraft("test-invitation")

        model.saveInvitation()
        runCurrent()

        assertEquals(listOf("test-invitation"), port.savedValues)
        assertEquals("test-invitation", model.uiState.value.invitationDraft)
        assertEquals("本机保存失败", model.uiState.value.invitationError)
        assertTrue(model.uiState.value.invitationExpanded)
        assertFalse(model.uiState.value.invitationSaving)
        assertFalse(model.uiState.value.invitationSaved)
    }

    @Test
    fun pending_save_rejects_duplicate_submissions_and_draft_changes() = runTest(dispatcher) {
        val completion = CompletableDeferred<InvitationSaveResult>()
        val port = FakeSessionPort()
        port.save = { completion.await() }
        val model = model(port)
        model.setInvitationDraft("original-invitation")

        model.saveInvitation()
        model.saveInvitation()
        model.setInvitationDraft("replacement")
        runCurrent()

        assertEquals(listOf("original-invitation"), port.savedValues)
        assertEquals("original-invitation", model.uiState.value.invitationDraft)
        assertTrue(model.uiState.value.invitationSaving)
        assertFalse(model.uiState.value.canEditInvitation)
        completion.complete(InvitationSaveResult.Saved)
        runCurrent()
        assertFalse(model.uiState.value.invitationSaving)
    }

    @Test
    fun successful_save_clears_draft_collapses_form_and_reports_saved_state() = runTest(dispatcher) {
        val port = FakeSessionPort()
        val model = model(port)
        model.setInvitationExpanded(true)
        model.setInvitationDraft("valid-invitation")

        model.saveInvitation()
        runCurrent()

        assertEquals("", model.uiState.value.invitationDraft)
        assertFalse(model.uiState.value.invitationExpanded)
        assertFalse(model.uiState.value.showInvitationForm)
        assertFalse(model.uiState.value.invitationSaving)
        assertTrue(model.uiState.value.invitationSaved)
        assertEquals(null, model.uiState.value.invitationError)
        assertEquals(DeviceSetupState.InvitationSaved, model.uiState.value.session.deviceSetup)
    }

    @Test
    fun blank_draft_shows_inline_error_without_calling_port() = runTest(dispatcher) {
        val port = FakeSessionPort()
        val model = model(port)
        model.setInvitationDraft("   ")
        model.saveInvitation()
        runCurrent()
        assertEquals("请输入邀请码", model.uiState.value.invitationError)
        assertTrue(port.savedValues.isEmpty())
        assertFalse(model.uiState.value.invitationSaving)
    }

    @Test
    fun unexpected_save_failure_is_presented_without_losing_draft() = runTest(dispatcher) {
        val port = FakeSessionPort()
        port.save = { throw IllegalStateException("private internal error") }
        val model = model(port)
        model.setInvitationDraft("retry-this")
        model.saveInvitation()
        runCurrent()
        assertEquals("retry-this", model.uiState.value.invitationDraft)
        assertEquals("邀请码保存失败，请重试", model.uiState.value.invitationError)
        assertFalse(model.uiState.value.invitationSaving)
    }

    @Test
    fun resubscribing_and_recreating_provider_preserve_in_memory_draft() = runTest(dispatcher) {
        val port = FakeSessionPort()
        val store = newStore()
        val model = ViewModelProvider(store, AgentViewModel.factory(port))[AgentViewModel::class.java]
        val firstValues = mutableListOf<String>()
        val first = launch(UnconfinedTestDispatcher(testScheduler)) {
            model.uiState.collect { firstValues.add(it.invitationDraft) }
        }
        model.setInvitationDraft("unsaved-invitation")
        first.cancel()

        val restored = ViewModelProvider(store, AgentViewModel.factory(port))[AgentViewModel::class.java]
        val secondValues = mutableListOf<String>()
        val second = launch(UnconfinedTestDispatcher(testScheduler)) {
            restored.uiState.collect { secondValues.add(it.invitationDraft) }
        }
        port.state.value = port.state.value.copy(accessibilityConnected = true)
        runCurrent()

        assertSame(model, restored)
        assertEquals("unsaved-invitation", restored.uiState.value.invitationDraft)
        assertEquals("unsaved-invitation", firstValues.last())
        assertTrue(secondValues.all { it == "unsaved-invitation" })
        assertTrue(restored.uiState.value.session.accessibilityConnected)
        second.cancel()
    }

    @Test
    fun disabling_entry_during_session_requires_confirmation_and_cancel_has_no_effect() = runTest(dispatcher) {
        val port = FakeSessionPort(ClientPhase.ShowingGuidance)
        val model = model(port)
        model.setEntryEnabled(false)
        runCurrent()
        assertTrue(model.uiState.value.confirmDisableEntry)
        assertTrue(port.entryChanges.isEmpty())
        assertEquals(0, port.endCalls)

        model.dismissDisableEntry()
        model.confirmDisableEntry()
        assertFalse(model.uiState.value.confirmDisableEntry)
        assertTrue(port.entryChanges.isEmpty())
        assertEquals(0, port.endCalls)
    }

    @Test
    fun confirmed_disable_delegates_once_to_session_controller() = runTest(dispatcher) {
        val port = FakeSessionPort(ClientPhase.WaitingForAgent)
        val model = model(port)
        model.setEntryEnabled(false)
        model.confirmDisableEntry()
        model.confirmDisableEntry()
        runCurrent()
        assertEquals(listOf(false), port.entryChanges)
        assertFalse(model.uiState.value.confirmDisableEntry)
    }

    @Test
    fun no_session_toggles_entry_without_confirmation() = runTest(dispatcher) {
        val port = FakeSessionPort()
        val model = model(port)
        model.setEntryEnabled(false)
        model.setEntryEnabled(true)
        runCurrent()
        assertEquals(listOf(false, true), port.entryChanges)
        assertFalse(model.uiState.value.confirmDisableEntry)
    }

    @Test
    fun session_completion_dismisses_obsolete_disable_confirmation() = runTest(dispatcher) {
        val port = FakeSessionPort(ClientPhase.Retry)
        val model = model(port)
        model.setEntryEnabled(false)
        port.state.value = port.state.value.copy(phase = ClientPhase.Setup)
        runCurrent()
        assertFalse(model.uiState.value.confirmDisableEntry)
        model.confirmDisableEntry()
        assertTrue(port.entryChanges.isEmpty())
    }

    @Test
    fun session_start_blocks_invitation_edits_and_save_without_discarding_draft() = runTest(dispatcher) {
        val port = FakeSessionPort()
        val model = model(port)
        model.setInvitationExpanded(true)
        model.setInvitationDraft("preserved-draft")
        port.state.value = port.state.value.copy(phase = ClientPhase.CreatingSession)
        runCurrent()

        model.setInvitationDraft("replacement")
        model.setInvitationExpanded(false)
        model.saveInvitation()
        runCurrent()

        assertEquals("preserved-draft", model.uiState.value.invitationDraft)
        assertTrue(model.uiState.value.invitationExpanded)
        assertFalse(model.uiState.value.showInvitationForm)
        assertFalse(model.uiState.value.canEditInvitation)
        assertTrue(port.savedValues.isEmpty())
    }

    private fun model(port: FakeSessionPort): AgentViewModel =
        ViewModelProvider(newStore(), AgentViewModel.factory(port))[AgentViewModel::class.java]

    private fun newStore(): ViewModelStore = ViewModelStore().also(stores::add)

    private class FakeSessionPort(phase: ClientPhase = ClientPhase.Setup) : AgentSessionPort {
        val state = MutableStateFlow(
            AgentClientUiState(phase = phase, deviceSetup = DeviceSetupState.MissingInvitation),
        )
        override val uiState: StateFlow<AgentClientUiState> = state
        val savedValues = mutableListOf<String>()
        val entryChanges = mutableListOf<Boolean>()
        var endCalls = 0
        var save: suspend (String) -> InvitationSaveResult = { InvitationSaveResult.Saved }

        override suspend fun saveInvitation(value: String): InvitationSaveResult {
            savedValues.add(value)
            return save(value).also { result ->
                if (result == InvitationSaveResult.Saved) {
                    state.value = state.value.copy(deviceSetup = DeviceSetupState.InvitationSaved)
                }
            }
        }

        override fun setEntryEnabled(enabled: Boolean) {
            entryChanges.add(enabled)
            state.value = state.value.copy(entryEnabled = enabled)
        }

        override fun endSession() {
            endCalls += 1
        }

        override fun refreshDeviceStatus() = Unit
    }
}
