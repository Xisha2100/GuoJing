package com.xisha.guojing.session

import kotlinx.coroutines.flow.StateFlow

/** Local readiness; Activated means credentials are stored, not a live server check. */
sealed interface DeviceSetupState {
    data object Loading : DeviceSetupState
    data object MissingInvitation : DeviceSetupState
    data object InvitationSaved : DeviceSetupState
    data object Activated : DeviceSetupState
    data class Blocked(val message: String) : DeviceSetupState
    data class Failed(val message: String) : DeviceSetupState
}

sealed interface InvitationSaveResult {
    data object Saved : InvitationSaveResult
    data class Failed(val message: String) : InvitationSaveResult
}

/** Home-screen actions; none of these methods begins screenshot recognition. */
interface AgentSessionPort {
    val uiState: StateFlow<AgentClientUiState>
    suspend fun saveInvitation(value: String): InvitationSaveResult
    fun refreshDeviceStatus()
    fun setEntryEnabled(enabled: Boolean)
    fun endSession()
}
