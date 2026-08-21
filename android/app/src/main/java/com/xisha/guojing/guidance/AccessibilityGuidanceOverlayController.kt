package com.xisha.guojing.guidance

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

class AccessibilityGuidanceOverlayController(
    context: Context,
) {
    private val windowManager = context.getSystemService(WindowManager::class.java)
    private val overlayView = GuidanceOverlayView(context)
    private var attached = false

    fun show(command: GuidanceOverlayCommand) {
        overlayView.command = command
        if (!attached) {
            windowManager.addView(overlayView, layoutParams())
            attached = true
        }
        overlayView.visibility = View.VISIBLE
        overlayView.invalidate()
    }

    fun temporarilyHide() {
        if (attached) overlayView.visibility = View.GONE
    }

    fun hide() {
        if (!attached) return
        windowManager.removeView(overlayView)
        attached = false
    }

    private fun layoutParams() = WindowManager.LayoutParams(
        WindowManager.LayoutParams.MATCH_PARENT,
        WindowManager.LayoutParams.MATCH_PARENT,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
        PixelFormat.TRANSLUCENT,
    ).apply {
        gravity = Gravity.TOP or Gravity.START
        title = "老牌子教程引导"
    }
}

private class GuidanceOverlayView(
    context: Context,
) : View(context) {
    var command: GuidanceOverlayCommand? = null
    private val planner = OverlayLayoutPlanner()
    private val density = resources.displayMetrics.density
    private val targetPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(176, 42, 42)
        style = Paint.Style.STROKE
        strokeWidth = 5f * density
    }
    private val targetFillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(45, 255, 214, 64)
        style = Paint.Style.FILL
    }
    private val cardPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(255, 248, 240)
        style = Paint.Style.FILL
        setShadowLayer(12f * density, 0f, 4f * density, Color.argb(90, 0, 0, 0))
    }
    private val cardBorderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(176, 42, 42)
        style = Paint.Style.STROKE
        strokeWidth = 3f * density
    }
    private val arrowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(176, 42, 42)
        style = Paint.Style.STROKE
        strokeWidth = 6f * density
        strokeCap = Paint.Cap.ROUND
    }
    private val stepPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(176, 42, 42)
        textSize = sp(20f)
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }
    private val instructionPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(32, 25, 22)
        textSize = sp(26f)
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }
    private val hintPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(94, 82, 76)
        textSize = sp(15f)
    }

    init {
        setLayerType(LAYER_TYPE_SOFTWARE, null)
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val current = command ?: return
        if (width <= 0 || height <= 0) return
        val viewportLocation = IntArray(2)
        getLocationOnScreen(viewportLocation)
        val layout = planner.plan(
            screenWidth = width,
            screenHeight = height,
            targetBounds = current.targetBounds,
            density = density,
            displayWidth = resources.displayMetrics.widthPixels,
            displayHeight = resources.displayMetrics.heightPixels,
            viewportLeft = viewportLocation[0],
            viewportTop = viewportLocation[1],
        )
        layout.targetRect?.let { target ->
            val rect = target.asRectF()
            canvas.drawRoundRect(rect, 16f * density, 16f * density, targetFillPaint)
            canvas.drawRoundRect(rect, 16f * density, 16f * density, targetPaint)
        }
        if (layout.arrowStart != null && layout.arrowEnd != null) {
            drawArrow(canvas, layout.arrowStart, layout.arrowEnd)
        }
        drawCard(canvas, current, layout.cardRect)
    }

    private fun drawCard(
        canvas: Canvas,
        current: GuidanceOverlayCommand,
        card: PixelRect,
    ) {
        val rect = card.asRectF()
        val radius = 24f * density
        canvas.drawRoundRect(rect, radius, radius, cardPaint)
        canvas.drawRoundRect(rect, radius, radius, cardBorderPaint)

        val horizontalPadding = 24f * density
        val contentWidth = (card.right - card.left - horizontalPadding * 2).toInt()
        var y = card.top + 16f * density
        y += drawText(
            canvas = canvas,
            text = "第 ${current.stepNumber} 步",
            paint = stepPaint,
            x = card.left + horizontalPadding,
            y = y,
            width = contentWidth,
            maxLines = 1,
        )
        y += 4f * density
        y += drawText(
            canvas = canvas,
            text = current.instruction,
            paint = instructionPaint,
            x = card.left + horizontalPadding,
            y = y,
            width = contentWidth,
            maxLines = 2,
        )
        y += 5f * density
        drawText(
            canvas = canvas,
            text = "请亲自操作 · 返回老牌子可退出",
            paint = hintPaint,
            x = card.left + horizontalPadding,
            y = y,
            width = contentWidth,
            maxLines = 1,
        )
    }

    private fun drawText(
        canvas: Canvas,
        text: String,
        paint: TextPaint,
        x: Float,
        y: Float,
        width: Int,
        maxLines: Int,
    ): Float {
        val layout = StaticLayout.Builder.obtain(text, 0, text.length, paint, width)
            .setAlignment(Layout.Alignment.ALIGN_NORMAL)
            .setIncludePad(false)
            .setEllipsize(TextUtils.TruncateAt.END)
            .setEllipsizedWidth(width)
            .setMaxLines(maxLines)
            .build()
        canvas.save()
        canvas.translate(x, y)
        layout.draw(canvas)
        canvas.restore()
        return layout.height.toFloat()
    }

    private fun drawArrow(canvas: Canvas, start: PixelPoint, end: PixelPoint) {
        canvas.drawLine(start.x, start.y, end.x, end.y, arrowPaint)
        val angle = atan2(end.y - start.y, end.x - start.x)
        val headLength = 22f * density
        val spread = Math.toRadians(28.0).toFloat()
        val path = Path().apply {
            moveTo(end.x, end.y)
            lineTo(
                end.x - headLength * cos(angle - spread),
                end.y - headLength * sin(angle - spread),
            )
            moveTo(end.x, end.y)
            lineTo(
                end.x - headLength * cos(angle + spread),
                end.y - headLength * sin(angle + spread),
            )
        }
        canvas.drawPath(path, arrowPaint)
    }

    private fun PixelRect.asRectF() = RectF(left, top, right, bottom)

    private fun sp(value: Float): Float = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_SP,
        value,
        resources.displayMetrics,
    )
}
