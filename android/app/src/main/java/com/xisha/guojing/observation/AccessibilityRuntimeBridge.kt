package com.xisha.guojing.observation

import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.guidance.OverlayActions
import com.xisha.guojing.guidance.OverlayPresentation
import com.xisha.guojing.model.CapturedScreen
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

interface ScreenCapturePort {
    val connected: StateFlow<Boolean>

    suspend fun capture(targetPackage: String): CapturedScreen

    fun isDisplayCurrent(
        targetPackage: String,
        displayWidth: Int,
        displayHeight: Int,
        rotation: Int,
    ): Boolean
}

internal interface AccessibilityHost {
    suspend fun capture(targetPackage: String): CapturedScreen

    fun isDisplayCurrent(
        targetPackage: String,
        displayWidth: Int,
        displayHeight: Int,
        rotation: Int,
    ): Boolean

    fun present(value: OverlayPresentation, actions: OverlayActions)

    fun hide()
}

object AccessibilityRuntimeBridge : ScreenCapturePort, GuidanceOverlayPort, OverlayActions {
    private val mutableConnected = MutableStateFlow(false)
    override val connected: StateFlow<Boolean> = mutableConnected.asStateFlow()

    private var host: AccessibilityHost? = null
    private var actions: OverlayActions? = null
    private var desired: OverlayPresentation = OverlayPresentation.Hidden

    internal fun attach(host: AccessibilityHost) {
        this.host = host
        mutableConnected.value = true
        host.present(desired, this)
    }

    internal fun detach(host: AccessibilityHost) {
        if (this.host !== host) return
        this.host = null
        mutableConnected.value = false
    }

    fun setActions(actions: OverlayActions) {
        this.actions = actions
    }

    override suspend fun capture(targetPackage: String): CapturedScreen =
        requireNotNull(host) { "Accessibility service is not connected" }
            .capture(targetPackage)

    override fun isDisplayCurrent(
        targetPackage: String,
        displayWidth: Int,
        displayHeight: Int,
        rotation: Int,
    ): Boolean = host?.isDisplayCurrent(
        targetPackage,
        displayWidth,
        displayHeight,
        rotation,
    ) == true

    override fun present(value: OverlayPresentation) {
        desired = value
        host?.present(value, this)
    }

    override fun hide() {
        desired = OverlayPresentation.Hidden
        host?.hide()
    }

    override fun onPrimaryAction() {
        actions?.onPrimaryAction()
    }

    override fun onReplay() {
        actions?.onReplay()
    }

    override fun onEndSession() {
        actions?.onEndSession()
    }
}
