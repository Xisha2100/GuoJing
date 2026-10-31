package com.xisha.guojing.ui

import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.ClientPhase
import com.xisha.guojing.session.DeviceSetupState

/** Presentation state. Invitation drafts live only in the activity's ViewModel. */
data class HomeUiState(
    val session: AgentClientUiState = AgentClientUiState(),
    val invitationDraft: String = "",
    val invitationExpanded: Boolean = false,
    val invitationSaving: Boolean = false,
    val invitationError: String? = null,
    val invitationSaved: Boolean = false,
    val confirmDisableEntry: Boolean = false,
) {
    val hasSession: Boolean get() = session.phase != ClientPhase.Setup
    val canEditInvitation: Boolean get() = !hasSession && !invitationSaving &&
        session.deviceSetup != DeviceSetupState.Loading
    val showInvitationForm: Boolean get() = !hasSession &&
        (invitationExpanded || session.deviceSetup == DeviceSetupState.MissingInvitation)
}

enum class PreparationAction { Loading, Invitation, Accessibility, Entry, Ready, Blocked, Failed }

/** Pure priority mapping; readiness describes local preparation, not remote authorization. */
fun nextPreparation(state: AgentClientUiState): PreparationAction = when (state.deviceSetup) {
    DeviceSetupState.Loading -> PreparationAction.Loading
    DeviceSetupState.MissingInvitation -> PreparationAction.Invitation
    is DeviceSetupState.Blocked -> PreparationAction.Blocked
    is DeviceSetupState.Failed -> PreparationAction.Failed
    DeviceSetupState.InvitationSaved, DeviceSetupState.Activated -> when {
        !state.accessibilityConnected -> PreparationAction.Accessibility
        !state.entryEnabled -> PreparationAction.Entry
        else -> PreparationAction.Ready
    }
}

fun devicePreparationLabel(state: DeviceSetupState): String = when (state) {
    DeviceSetupState.Loading -> "正在读取本机资料"
    DeviceSetupState.MissingInvitation -> "尚未保存邀请码"
    DeviceSetupState.InvitationSaved -> "已保存，首次确认目标时激活"
    DeviceSetupState.Activated -> "本机已开通"
    is DeviceSetupState.Blocked -> state.message
    is DeviceSetupState.Failed -> state.message
}
