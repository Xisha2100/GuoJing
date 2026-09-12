package com.xisha.guojing.observation

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.hardware.HardwareBuffer
import android.view.Display
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import com.xisha.guojing.guidance.AccessibilityGuidanceOverlayController
import com.xisha.guojing.guidance.OverlayActions
import com.xisha.guojing.guidance.OverlayPresentation
import com.xisha.guojing.model.CapturedScreen
import java.io.ByteArrayOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

class GuoJingAccessibilityService : AccessibilityService(), AccessibilityHost {
    private var overlayController: AccessibilityGuidanceOverlayController? = null
    private var presentation: OverlayPresentation = OverlayPresentation.Hidden
    private var actions: OverlayActions? = null
    private var captureInProgress = false

    override fun onServiceConnected() {
        super.onServiceConnected()
        overlayController = AccessibilityGuidanceOverlayController(this)
        AccessibilityRuntimeBridge.attach(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        if (presentation is OverlayPresentation.Hidden) return
        updateOverlayVisibility()
    }

    override fun onInterrupt() {
        overlayController?.temporarilyHide()
    }

    override suspend fun capture(targetPackage: String): CapturedScreen {
        check(!captureInProgress)
        captureInProgress = true
        overlayController?.temporarilyHide()
        try {
            delay(OVERLAY_SETTLE_MILLIS)
            check(foregroundPackage() == targetPackage) {
                "Target application is not in the foreground"
            }
            val rotation = currentRotation()
            val raw = takeRawScreenshot()
            var encoded: CapturedScreen? = null
            try {
                raw.use {
                    withContext(Dispatchers.Default) {
                        encoded = encodeScreenshot(it, rotation)
                    }
                }
                check(foregroundPackage() == targetPackage && currentRotation() == rotation)
                return requireNotNull(encoded)
            } catch (error: Throwable) {
                encoded?.erase()
                throw error
            }
        } finally {
            captureInProgress = false
            updateOverlayVisibility()
        }
    }

    override fun present(value: OverlayPresentation, actions: OverlayActions) {
        presentation = value
        this.actions = actions
        updateOverlayVisibility()
    }

    override fun hide() {
        presentation = OverlayPresentation.Hidden
        overlayController?.hide()
    }

    override fun isDisplayCurrent(
        targetPackage: String,
        displayWidth: Int,
        displayHeight: Int,
        rotation: Int,
    ): Boolean {
        val bounds = getSystemService(WindowManager::class.java).currentWindowMetrics.bounds
        return foregroundPackage() == targetPackage &&
            bounds.width() == displayWidth &&
            bounds.height() == displayHeight &&
            currentRotation() == rotation
    }

    override fun onDestroy() {
        AccessibilityRuntimeBridge.detach(this)
        overlayController?.hide()
        overlayController = null
        actions = null
        super.onDestroy()
    }

    private fun updateOverlayVisibility() {
        if (captureInProgress) {
            overlayController?.temporarilyHide()
            return
        }
        val value = presentation
        if (value is OverlayPresentation.Hidden) {
            overlayController?.hide()
            return
        }
        if (foregroundPackage() == value.targetPackage()) {
            val visible = if (value is OverlayPresentation.Guidance && !isDisplayCurrent(
                    value.targetPackage, value.displayWidth, value.displayHeight, value.rotation,
                )
            ) {
                OverlayPresentation.Retry(value.targetPackage, "屏幕方向已变化，请重新识别")
            } else {
                value
            }
            overlayController?.present(visible, requireNotNull(actions))
        } else {
            overlayController?.temporarilyHide()
        }
    }

    private fun foregroundPackage(): String? =
        rootInActiveWindow?.packageName?.toString()

    private suspend fun takeRawScreenshot(): RawScreenshot = suspendCancellableCoroutine {
        continuation ->
        takeScreenshot(
            Display.DEFAULT_DISPLAY,
            mainExecutor,
            object : TakeScreenshotCallback {
                override fun onSuccess(screenshot: ScreenshotResult) {
                    if (continuation.isActive) {
                        continuation.resume(
                            RawScreenshot(screenshot.hardwareBuffer, screenshot.colorSpace),
                        )
                    } else {
                        screenshot.hardwareBuffer.close()
                    }
                }

                override fun onFailure(errorCode: Int) {
                    if (continuation.isActive) {
                        continuation.resumeWithException(
                            ScreenCaptureException("Screenshot failed", errorCode),
                        )
                    }
                }
            },
        )
    }

    private fun encodeScreenshot(raw: RawScreenshot, rotation: Int): CapturedScreen {
        val hardwareBitmap = Bitmap.wrapHardwareBuffer(raw.buffer, raw.colorSpace)
            ?: throw ScreenCaptureException("Unable to read screenshot")
        try {
            val source = hardwareBitmap.copy(Bitmap.Config.ARGB_8888, false)
                ?: throw ScreenCaptureException("Unable to copy screenshot")
            try {
                val displayWidth = source.width
                val displayHeight = source.height
                val scale = (MAX_SCREEN_DIMENSION.toFloat() / maxOf(source.width, source.height))
                    .coerceAtMost(1f)
                val width = (source.width * scale).roundToInt()
                val height = (source.height * scale).roundToInt()
                val resized = if (width == source.width && height == source.height) {
                    source
                } else {
                    Bitmap.createScaledBitmap(source, width, height, true)
                }
                try {
                    val bytes = ByteArrayOutputStream().use { output ->
                        check(resized.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output))
                        output.toByteArray()
                    }
                    if (bytes.size > MAX_ENCODED_BYTES) {
                        bytes.fill(0)
                        throw ScreenCaptureException("Screenshot is too large")
                    }
                    return CapturedScreen(
                        jpegBytes = bytes,
                        width = resized.width,
                        height = resized.height,
                        displayWidth = displayWidth,
                        displayHeight = displayHeight,
                        rotation = rotation,
                    )
                } finally {
                    if (resized !== source) resized.recycle()
                }
            } finally {
                source.recycle()
            }
        } finally {
            hardwareBitmap.recycle()
        }
    }

    private fun currentRotation(): Int = captureDisplayRotation(this)

    private fun OverlayPresentation.targetPackage(): String = when (this) {
        OverlayPresentation.Hidden -> ""
        is OverlayPresentation.Ready -> targetPackage
        is OverlayPresentation.Loading -> targetPackage
        is OverlayPresentation.Guidance -> targetPackage
        is OverlayPresentation.Retry -> targetPackage
        is OverlayPresentation.Completed -> targetPackage
    }

    private companion object {
        const val OVERLAY_SETTLE_MILLIS = 120L
        const val MAX_SCREEN_DIMENSION = 1440
        const val MAX_ENCODED_BYTES = 8 * 1024 * 1024
        const val JPEG_QUALITY = 85
    }
}

class ScreenCaptureException(
    message: String,
    val platformErrorCode: Int? = null,
) : IllegalStateException(message)

private class RawScreenshot(
    val buffer: HardwareBuffer,
    val colorSpace: android.graphics.ColorSpace,
) : AutoCloseable {
    override fun close() {
        buffer.close()
    }
}
