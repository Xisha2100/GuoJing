package com.xisha.guojing.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.xisha.guojing.session.AgentSessionPort
import com.xisha.guojing.session.ClientPhase
import com.xisha.guojing.session.InvitationSaveResult
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class AgentViewModel(private val controller: AgentSessionPort) : ViewModel() {
    private val mutableUiState = MutableStateFlow(HomeUiState(session = controller.uiState.value))
    val uiState: StateFlow<HomeUiState> = mutableUiState.asStateFlow()

    init {
        viewModelScope.launch {
            controller.uiState.collect { session ->
                mutableUiState.update {
                    it.copy(
                        session = session,
                        confirmDisableEntry = it.confirmDisableEntry &&
                            session.phase != ClientPhase.Setup,
                    )
                }
            }
        }
    }

    fun setInvitationDraft(value: String) {
        if (!mutableUiState.value.canEditInvitation) return
        mutableUiState.update {
            it.copy(invitationDraft = value, invitationError = null, invitationSaved = false)
        }
    }

    fun setInvitationExpanded(expanded: Boolean) {
        if (!mutableUiState.value.canEditInvitation) return
        mutableUiState.update { it.copy(invitationExpanded = expanded, invitationSaved = false) }
    }

    fun saveInvitation() {
        val state = mutableUiState.value
        if (!state.canEditInvitation) return
        if (state.invitationDraft.isBlank()) {
            mutableUiState.update { it.copy(invitationError = "请输入邀请码") }
            return
        }
        mutableUiState.update {
            it.copy(invitationSaving = true, invitationError = null, invitationSaved = false)
        }
        viewModelScope.launch {
            try {
                when (val result = controller.saveInvitation(state.invitationDraft)) {
                    InvitationSaveResult.Saved -> mutableUiState.update {
                        it.copy(
                            invitationDraft = "", invitationExpanded = false,
                            invitationSaved = true, invitationError = null,
                        )
                    }
                    is InvitationSaveResult.Failed -> mutableUiState.update {
                        it.copy(invitationError = result.message)
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                mutableUiState.update { it.copy(invitationError = "邀请码保存失败，请重试") }
            } finally {
                mutableUiState.update { it.copy(invitationSaving = false) }
            }
        }
    }

    fun setEntryEnabled(value: Boolean) {
        if (!value && controller.uiState.value.phase != ClientPhase.Setup) {
            mutableUiState.update { it.copy(confirmDisableEntry = true) }
        } else {
            controller.setEntryEnabled(value)
        }
    }

    fun confirmDisableEntry() {
        if (!mutableUiState.value.confirmDisableEntry) return
        mutableUiState.update { it.copy(confirmDisableEntry = false) }
        controller.setEntryEnabled(false)
    }

    fun dismissDisableEntry() {
        mutableUiState.update { it.copy(confirmDisableEntry = false) }
    }

    fun refreshDeviceStatus() = controller.refreshDeviceStatus()
    fun endSession() = controller.endSession()

    companion object {
        fun factory(controller: AgentSessionPort): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    AgentViewModel(controller) as T
            }
    }
}
