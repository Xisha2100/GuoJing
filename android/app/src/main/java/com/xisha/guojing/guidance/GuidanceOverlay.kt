package com.xisha.guojing.guidance

import com.xisha.guojing.model.NormalizedTarget
import com.xisha.guojing.model.TargetApp

sealed interface OverlayPresentation {
    data object Hidden : OverlayPresentation
    data object Entry : OverlayPresentation

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
    fun onStartInApp(app: TargetApp, goal: String) {}
    fun onTargetLeft() {}
    fun onPrimaryAction()

    fun onReplay()

    fun onEndSession()
}

interface GuidanceOverlayPort {
    fun showMessage(message: String) {}
    fun showSpeechRange(start: Int, end: Int) {}
    fun present(value: OverlayPresentation)

    fun hide()
}
