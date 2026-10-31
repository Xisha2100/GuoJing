package com.xisha.guojing.ui

import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.ClientPhase
import com.xisha.guojing.session.DeviceSetupState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeUiStateTest {
    @Test
    fun device_preparation_takes_priority_over_service_and_entry() {
        val cases = listOf(
            DeviceSetupState.Loading to PreparationAction.Loading,
            DeviceSetupState.MissingInvitation to PreparationAction.Invitation,
            DeviceSetupState.Blocked("授权已到期") to PreparationAction.Blocked,
            DeviceSetupState.Failed("本机资料读取失败") to PreparationAction.Failed,
        )
        for ((device, expected) in cases) {
            for (connected in listOf(false, true)) {
                for (entry in listOf(false, true)) {
                    val state = AgentClientUiState(
                        deviceSetup = device,
                        accessibilityConnected = connected,
                        entryEnabled = entry,
                    )
                    assertEquals("device=$device connected=$connected entry=$entry", expected, nextPreparation(state))
                }
            }
        }
    }

    @Test
    fun saved_invitation_and_activated_device_share_local_readiness_order() {
        for (device in listOf(DeviceSetupState.InvitationSaved, DeviceSetupState.Activated)) {
            val state = AgentClientUiState(deviceSetup = device, entryEnabled = false)
            assertEquals(PreparationAction.Accessibility, nextPreparation(state))
            assertEquals(
                PreparationAction.Entry,
                nextPreparation(state.copy(accessibilityConnected = true)),
            )
            assertEquals(
                PreparationAction.Ready,
                nextPreparation(state.copy(accessibilityConnected = true, entryEnabled = true)),
            )
        }
    }

    @Test
    fun temporary_operation_error_does_not_change_device_readiness() {
        val state = AgentClientUiState(
            deviceSetup = DeviceSetupState.Activated,
            accessibilityConnected = true,
            entryEnabled = true,
            message = "服务繁忙，请稍后重试",
        )
        assertEquals(PreparationAction.Ready, nextPreparation(state))
        assertEquals("本机已开通", devicePreparationLabel(state.deviceSetup))
    }

    @Test
    fun invitation_form_opens_for_missing_invitation_and_collapses_after_saved() {
        val missing = HomeUiState(session = AgentClientUiState(deviceSetup = DeviceSetupState.MissingInvitation))
        assertTrue(missing.showInvitationForm)
        assertTrue(missing.canEditInvitation)
        val saved = missing.copy(session = missing.session.copy(deviceSetup = DeviceSetupState.InvitationSaved))
        assertFalse(saved.showInvitationForm)
        assertTrue(saved.copy(invitationExpanded = true).showInvitationForm)
    }

    @Test
    fun reading_or_saving_disables_invitation_edits() {
        assertFalse(HomeUiState().canEditInvitation)
        assertFalse(
            HomeUiState(
                session = AgentClientUiState(deviceSetup = DeviceSetupState.MissingInvitation),
                invitationSaving = true,
            ).canEditInvitation,
        )
    }

    @Test
    fun every_non_setup_phase_hides_form_and_disables_edits() {
        for (phase in ClientPhase.entries.filter { it != ClientPhase.Setup }) {
            val state = HomeUiState(
                session = AgentClientUiState(phase = phase, deviceSetup = DeviceSetupState.MissingInvitation),
                invitationExpanded = true,
            )
            assertTrue("phase=$phase", state.hasSession)
            assertFalse("phase=$phase", state.showInvitationForm)
            assertFalse("phase=$phase", state.canEditInvitation)
        }
    }
}
