package com.xisha.guojing.observation

import android.accessibilityservice.AccessibilityService
import android.app.AlertDialog
import android.app.KeyguardManager
import android.text.InputFilter
import android.view.accessibility.AccessibilityWindowInfo
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import android.graphics.Bitmap
import android.hardware.HardwareBuffer
import android.view.Display
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import com.xisha.guojing.guidance.AccessibilityGuidanceOverlayController
import com.xisha.guojing.guidance.OverlayActions
import com.xisha.guojing.guidance.OverlayPresentation
import com.xisha.guojing.model.CapturedScreen
import com.xisha.guojing.model.TargetApp
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
    private var presentation: OverlayPresentation = OverlayPresentation.Entry
    private var actions: OverlayActions? = null
    private var captureInProgress = false
    private var goalDialog: AlertDialog? = null
    private var previousPackage: String? = null

    override fun showMessage(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    override fun showSpeechRange(start: Int, end: Int) {
        overlayController?.showSpeechRange(start, end)
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        overlayController = AccessibilityGuidanceOverlayController(this)
        AccessibilityRuntimeBridge.attach(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        if (presentation is OverlayPresentation.Hidden) return
        val current = foregroundPackage()
        if (current != previousPackage && goalDialog == null) {
            previousPackage = current
            actions?.onTargetLeft()
        }
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
        goalDialog?.dismiss()
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
        goalDialog?.dismiss()
        AccessibilityRuntimeBridge.detach(this)
        overlayController?.hide()
        overlayController = null
        actions = null
        super.onDestroy()
    }

    private fun updateOverlayVisibility() {
        if (getSystemService(KeyguardManager::class.java).isKeyguardLocked) {
            goalDialog?.dismiss()
            overlayController?.temporarilyHide()
            actions?.onTargetLeft()
            return
        }
        if (goalDialog != null) return
        if (captureInProgress) {
            overlayController?.temporarilyHide()
            return
        }
        val value = presentation
        if (value is OverlayPresentation.Hidden) {
            overlayController?.hide()
            return
        }
        val foreground = foregroundPackage()
        if (foreground == null || foreground == packageName) {
            overlayController?.temporarilyHide()
            return
        }
        if (value is OverlayPresentation.Entry || foreground != value.targetPackage()) {
            overlayController?.present(OverlayPresentation.Entry, object : OverlayActions {
                override fun onPrimaryAction() = openGoalInput()
                override fun onReplay() {}
                override fun onEndSession() {}
            })
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

    private fun foregroundWindow(): AccessibilityWindowInfo? = windows.firstOrNull {
        it.type == AccessibilityWindowInfo.TYPE_APPLICATION && (it.isFocused || it.isActive) &&
            it.root?.packageName?.toString() !in setOf(packageName, "com.android.systemui")
    }

    private fun foregroundPackage(): String? = foregroundWindow()?.root?.packageName?.toString()

    private fun openGoalInput() {
        if (goalDialog != null) return
        val window = foregroundWindow() ?: return
        val targetPackage = window.root?.packageName?.toString() ?: return
        val windowId = window.id
        val label = runCatching {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(targetPackage, 0)).toString()
        }.getOrDefault(targetPackage)
        actions?.onTargetLeft()
        overlayController?.temporarilyHide()
        val input = EditText(this).apply {
            hint = "例如：帮我找到扫一扫"
            filters = arrayOf(InputFilter.LengthFilter(500))
            minLines = 2
            maxLines = 5
        }
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (20 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
            addView(TextView(this@GuoJingAccessibilityService).apply { text = "当前应用：$label" })
            addView(input)
            addView(TextView(this@GuoJingAccessibilityService).apply {
                text = "开始后会上传当前截图，生成一步指引。"
            })
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle("你想完成什么？")
            .setView(body)
            .setNegativeButton("取消", null)
            .setPositiveButton("开始指引", null)
            .create()
        dialog.window?.setType(WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY)
        dialog.setOnDismissListener {
            goalDialog = null
            updateOverlayVisibility()
        }
        goalDialog = dialog
        dialog.show()
        dialog.window?.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        input.requestFocus()
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val goal = input.text.toString().trim()
            if (goal.isBlank()) {
                input.error = "请先输入目标"
            } else {
                getSystemService(android.view.inputmethod.InputMethodManager::class.java)
                    .hideSoftInputFromWindow(input.windowToken, 0)
                dialog.dismiss()
                android.os.Handler(mainLooper).postDelayed({
                    val current = foregroundWindow()
                    if (current?.id == windowId && foregroundPackage() == targetPackage) {
                        actions?.onStartInApp(TargetApp(targetPackage, label), goal)
                    } else {
                        Toast.makeText(this, "应用已切换，请重新点击悬浮入口", Toast.LENGTH_SHORT).show()
                    }
                }, 250)
            }
        }
    }

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
        OverlayPresentation.Entry -> ""
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
