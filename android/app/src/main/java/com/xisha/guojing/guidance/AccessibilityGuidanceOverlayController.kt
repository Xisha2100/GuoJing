package com.xisha.guojing.guidance

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

class AccessibilityGuidanceOverlayController(
    private val context: Context,
) {
    private val windowManager = context.getSystemService(WindowManager::class.java)
    private val instructionView = GuidanceOverlayView(context)
    private val controls = ControlView(context)
    private var instructionAttached = false
    private var controlsAttached = false
    private var current: OverlayPresentation = OverlayPresentation.Hidden

    fun present(value: OverlayPresentation, actions: OverlayActions) {
        current = value
        if (value is OverlayPresentation.Hidden) {
            hide()
            return
        }
        if (value is OverlayPresentation.Guidance) {
            instructionView.guidance = value
            attachInstruction()
            instructionView.visibility = View.VISIBLE
            instructionView.invalidate()
        } else {
            instructionView.visibility = View.GONE
        }
        controls.bind(value, actions)
        attachControls(value)
        controls.visibility = View.VISIBLE
    }

    fun temporarilyHide() {
        instructionView.visibility = View.GONE
        controls.visibility = View.GONE
    }

    fun restoreIfAttached() {
        if (current !is OverlayPresentation.Hidden) {
            instructionView.visibility =
                if (current is OverlayPresentation.Guidance) View.VISIBLE else View.GONE
            controls.visibility = View.VISIBLE
        }
    }

    fun hide() {
        if (instructionAttached) {
            windowManager.removeView(instructionView)
            instructionAttached = false
        }
        if (controlsAttached) {
            windowManager.removeView(controls)
            controlsAttached = false
        }
    }

    private fun attachInstruction() {
        if (instructionAttached) return
        windowManager.addView(
            instructionView,
            WindowManager.LayoutParams(
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
                title = "老牌子视觉指引"
            },
        )
        instructionAttached = true
    }

    private fun attachControls(value: OverlayPresentation) {
        val params = controlLayoutParams(value)
        if (!controlsAttached) {
            windowManager.addView(controls, params)
            controlsAttached = true
        } else {
            windowManager.updateViewLayout(controls, params)
        }
    }

    private fun controlLayoutParams(value: OverlayPresentation): WindowManager.LayoutParams {
        val metrics = context.resources.displayMetrics
        val target = (value as? OverlayPresentation.Guidance)?.target
        val targetOnRight = target?.let { (it.left + it.right) / 2.0 >= 0.5 } ?: false
        return WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = if (targetOnRight) {
                dp(16)
            } else {
                (metrics.widthPixels - dp(CONTROL_WIDTH_DP + 16)).coerceAtLeast(dp(16))
            }
            y = (metrics.heightPixels * 0.42f).toInt()
            title = "老牌子操作胶囊"
        }
    }

    private fun dp(value: Int): Int = (value * context.resources.displayMetrics.density).toInt()

    private companion object {
        const val CONTROL_WIDTH_DP = 280
    }
}

private class ControlView(context: Context) : LinearLayout(context) {
    private val status = TextView(context).apply {
        setTextColor(Color.rgb(38, 31, 27))
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
        setTypeface(typeface, Typeface.BOLD)
        maxLines = 2
    }
    private val primary = Button(context)
    private val replay = Button(context).apply { text = "重播" }
    private val end = Button(context).apply { text = "结束" }

    init {
        orientation = VERTICAL
        gravity = Gravity.CENTER
        setPadding(dp(12), dp(10), dp(12), dp(10))
        background = GradientDrawable().apply {
            setColor(Color.rgb(255, 248, 240))
            cornerRadius = dp(22).toFloat()
            setStroke(dp(2), Color.rgb(176, 42, 42))
        }
        elevation = dp(8).toFloat()
        addView(status, LayoutParams(dp(255), LayoutParams.WRAP_CONTENT))
        addView(
            LinearLayout(context).apply {
                orientation = HORIZONTAL
                gravity = Gravity.CENTER
                addView(primary)
                addView(replay)
                addView(end)
            },
        )
    }

    fun bind(value: OverlayPresentation, actions: OverlayActions) {
        when (value) {
            OverlayPresentation.Hidden -> Unit
            is OverlayPresentation.Ready -> {
                status.text = "已打开 ${value.targetLabel} 后，点击开始"
                primary.text = "开始识别"
                primary.isEnabled = true
                replay.visibility = GONE
            }

            is OverlayPresentation.Loading -> {
                status.text = "正在识别当前界面，请稍候"
                primary.text = "识别中…"
                primary.isEnabled = false
                replay.visibility = GONE
            }

            is OverlayPresentation.Guidance -> {
                status.text = "第 ${value.stepNumber} 步"
                primary.text = "我已完成"
                primary.isEnabled = true
                replay.visibility = VISIBLE
            }

            is OverlayPresentation.Retry -> {
                status.text = value.message
                primary.text = "重新识别"
                primary.isEnabled = true
                replay.visibility = VISIBLE
            }

            is OverlayPresentation.Completed -> {
                status.text = value.message
                primary.text = "完成"
                primary.isEnabled = true
                replay.visibility = VISIBLE
            }
        }
        primary.setOnClickListener { actions.onPrimaryAction() }
        replay.setOnClickListener { actions.onReplay() }
        end.setOnClickListener { actions.onEndSession() }
        contentDescription = status.text
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}

private class GuidanceOverlayView(context: Context) : View(context) {
    var guidance: OverlayPresentation.Guidance? = null
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
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
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
    private val stepPaint = textPaint(20f, Color.rgb(176, 42, 42))
    private val instructionPaint = textPaint(26f, Color.rgb(32, 25, 22))

    init {
        setLayerType(LAYER_TYPE_SOFTWARE, null)
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    override fun onDraw(canvas: Canvas) {
        val current = guidance ?: return
        if (width <= 0 || height <= 0) return
        val location = IntArray(2)
        getLocationOnScreen(location)
        val layout = planner.plan(
            screenWidth = width,
            screenHeight = height,
            targetBounds = current.target,
            density = density,
            displayWidth = current.displayWidth,
            displayHeight = current.displayHeight,
            viewportLeft = location[0],
            viewportTop = location[1],
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
        current: OverlayPresentation.Guidance,
        card: PixelRect,
    ) {
        val rect = card.asRectF()
        canvas.drawRoundRect(rect, 24f * density, 24f * density, cardPaint)
        canvas.drawRoundRect(rect, 24f * density, 24f * density, borderPaint)
        val padding = 24f * density
        val contentWidth = (card.right - card.left - padding * 2).toInt()
        var y = card.top + 18f * density
        y += drawText(canvas, "第 ${current.stepNumber} 步", stepPaint, card.left + padding, y, contentWidth, 1)
        drawText(canvas, current.instruction, instructionPaint, card.left + padding, y + 6f * density, contentWidth, 3)
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
        val length = 22f * density
        val spread = Math.toRadians(28.0).toFloat()
        val path = Path().apply {
            moveTo(end.x, end.y)
            lineTo(end.x - length * cos(angle - spread), end.y - length * sin(angle - spread))
            moveTo(end.x, end.y)
            lineTo(end.x - length * cos(angle + spread), end.y - length * sin(angle + spread))
        }
        canvas.drawPath(path, arrowPaint)
    }

    private fun textPaint(size: Float, color: Int) = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        this.color = color
        textSize = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_SP,
            size,
            resources.displayMetrics,
        )
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }

    private fun PixelRect.asRectF() = RectF(left, top, right, bottom)
}
