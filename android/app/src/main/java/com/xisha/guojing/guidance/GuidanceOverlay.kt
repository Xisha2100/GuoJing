package com.xisha.guojing.guidance

import com.xisha.guojing.model.NormalizedTarget

sealed interface OverlayPresentation {
    data object Hidden : OverlayPresentation

    data class Ready(
        val targetPackage: String,
        val targetLabel: String,
    ) : OverlayPresentation

    data class Loading(
        val targetPackage: String,
    ) : OverlayPresentation

    data class Guidance(
        val targetPackage: String,
        val stepNumber: Int,
        val instruction: String,
        val target: NormalizedTarget,
        val displayWidth: Int,
        val displayHeight: Int,
        val rotation: Int,
    ) : OverlayPresentation

    data class Retry(
        val targetPackage: String,
        val message: String,
    ) : OverlayPresentation

    data class Completed(
        val targetPackage: String,
        val message: String,
    ) : OverlayPresentation
}

interface OverlayActions {
    fun onPrimaryAction()

    fun onReplay()

    fun onEndSession()
}

interface GuidanceOverlayPort {
    fun present(value: OverlayPresentation)

    fun hide()
}
