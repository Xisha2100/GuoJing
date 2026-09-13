package com.xisha.guojing.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.xisha.guojing.session.AgentSessionController

class AgentViewModel(private val controller: AgentSessionController) : ViewModel() {
    val uiState = controller.uiState
    fun setEntryEnabled(value: Boolean) = controller.setEntryEnabled(value)
    fun endSession() = controller.endSession()

    companion object {
        fun factory(controller: AgentSessionController): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T =
                    AgentViewModel(controller) as T
            }
    }
}
