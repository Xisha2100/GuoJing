package com.xisha.guojing.guidance

import com.xisha.guojing.observation.NormalizedScreenBounds
import kotlin.math.min

data class PixelPoint(
    val x: Float,
    val y: Float,
)

data class PixelRect(
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
) {
    val centerX: Float get() = (left + right) / 2f
    val centerY: Float get() = (top + bottom) / 2f
}

data class OverlayLayout(
    val targetRect: PixelRect?,
    val cardRect: PixelRect,
    val arrowStart: PixelPoint?,
    val arrowEnd: PixelPoint?,
)

class OverlayLayoutPlanner {
    fun plan(
        screenWidth: Int,
        screenHeight: Int,
        targetBounds: NormalizedScreenBounds?,
        density: Float,
        displayWidth: Int = screenWidth,
        displayHeight: Int = screenHeight,
        viewportLeft: Int = 0,
        viewportTop: Int = 0,
    ): OverlayLayout {
        require(screenWidth > 0 && screenHeight > 0 && displayWidth > 0 && displayHeight > 0)
        val margin = 20f * density
        val cardHeight = min(180f * density, screenHeight * 0.28f)
        val card = cardRect(
            screenWidth = screenWidth,
            screenHeight = screenHeight,
            targetBounds = targetBounds,
            margin = margin,
            height = cardHeight,
        )
        val target = targetBounds?.toPixelRect(
            screenWidth = screenWidth,
            screenHeight = screenHeight,
            displayWidth = displayWidth,
            displayHeight = displayHeight,
            viewportLeft = viewportLeft,
            viewportTop = viewportTop,
            padding = 8f * density,
        )
        val start = target?.let {
            PixelPoint(
                x = card.centerX,
                y = if (card.centerY < it.centerY) card.bottom else card.top,
            )
        }
        val end = target?.let { PixelPoint(it.centerX, it.centerY) }
        return OverlayLayout(
            targetRect = target,
            cardRect = card,
            arrowStart = start,
            arrowEnd = end,
        )
    }

    private fun cardRect(
        screenWidth: Int,
        screenHeight: Int,
        targetBounds: NormalizedScreenBounds?,
        margin: Float,
        height: Float,
    ): PixelRect {
        val placeAtTop = targetBounds != null &&
            (targetBounds.top + targetBounds.bottom) / 2 > 0.5
        val top = if (placeAtTop) margin else screenHeight - margin - height
        return PixelRect(
            left = margin,
            top = top,
            right = screenWidth - margin,
            bottom = top + height,
        )
    }

    private fun NormalizedScreenBounds.toPixelRect(
        screenWidth: Int,
        screenHeight: Int,
        displayWidth: Int,
        displayHeight: Int,
        viewportLeft: Int,
        viewportTop: Int,
        padding: Float,
    ): PixelRect = PixelRect(
        left = (left.toFloat() * displayWidth - viewportLeft - padding)
            .coerceIn(0f, screenWidth.toFloat()),
        top = (top.toFloat() * displayHeight - viewportTop - padding)
            .coerceIn(0f, screenHeight.toFloat()),
        right = (right.toFloat() * displayWidth - viewportLeft + padding)
            .coerceIn(0f, screenWidth.toFloat()),
        bottom = (bottom.toFloat() * displayHeight - viewportTop + padding)
            .coerceIn(0f, screenHeight.toFloat()),
    )
}
