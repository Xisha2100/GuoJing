package com.xisha.guojing.guidance

import com.xisha.guojing.observation.NormalizedScreenBounds
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class GuidanceOverlayCommand(
    val targetPackageName: String,
    val stepNumber: Int,
    val instruction: String,
    val targetBounds: NormalizedScreenBounds?,
    /** Identity of the observation that justified this visible command. */
    val graphId: String = "",
    val nodeId: String = "",
    val observationSequence: Long = 0L,
)

sealed interface GuidanceOverlayState {
    data object Hidden : GuidanceOverlayState

    data class Visible(
        val sequence: Long,
        val command: GuidanceOverlayCommand,
    ) : GuidanceOverlayState
}

interface GuidanceOverlayPort {
    val state: StateFlow<GuidanceOverlayState>

    fun show(command: GuidanceOverlayCommand)

    fun hide()
}

object AccessibilityGuidanceCoordinator : GuidanceOverlayPort {
    private val mutableState = MutableStateFlow<GuidanceOverlayState>(
        GuidanceOverlayState.Hidden,
    )
    override val state: StateFlow<GuidanceOverlayState> = mutableState.asStateFlow()
    private var commandSequence = 0L

    override fun show(command: GuidanceOverlayCommand) {
        commandSequence += 1
        mutableState.value = GuidanceOverlayState.Visible(commandSequence, command)
    }

    override fun hide() {
        mutableState.value = GuidanceOverlayState.Hidden
    }
}

object DisabledGuidanceOverlayPort : GuidanceOverlayPort {
    private val hiddenState = MutableStateFlow<GuidanceOverlayState>(
        GuidanceOverlayState.Hidden,
    )
    override val state: StateFlow<GuidanceOverlayState> = hiddenState.asStateFlow()

    override fun show(command: GuidanceOverlayCommand) = Unit

    override fun hide() = Unit
}
