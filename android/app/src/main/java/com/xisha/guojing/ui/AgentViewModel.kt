package com.xisha.guojing.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.xisha.guojing.session.AgentSessionController

class AgentViewModel(
    private val controller: AgentSessionController,
) : ViewModel() {
    val uiState = controller.uiState

    fun updateGoal(value: String) = controller.updateGoal(value)

    fun selectApp(packageName: String) = controller.selectApp(packageName)

    fun setUploadConsent(value: Boolean) = controller.setUploadConsent(value)

    fun startSession() = controller.startSession()

    fun openTargetApp() = controller.openTargetApp()

    fun requestGuidance() = controller.requestGuidance()

    fun endSession() = controller.endSession()

    companion object {
        fun factory(controller: AgentSessionController): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    require(modelClass.isAssignableFrom(AgentViewModel::class.java))
                    return AgentViewModel(controller) as T
                }
            }
    }
}
