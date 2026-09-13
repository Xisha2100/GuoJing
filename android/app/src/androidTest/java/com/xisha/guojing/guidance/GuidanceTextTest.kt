package com.xisha.guojing.guidance

import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.SystemClock
import androidx.test.platform.app.InstrumentationRegistry
import com.xisha.guojing.model.NormalizedTarget
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GuidanceTextTest {
    @Test
    fun complete_text_scrolls_to_last_line_and_replay_resets_at_large_font_sizes() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        for (scale in listOf(1f, 2f)) {
            for ((width, height) in listOf(1080 to 2400, 2400 to 1080)) {
                lateinit var view: GuidanceOverlayView
                val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                val text = "请点击右上角的设置按钮，确认名称后再操作。".repeat(20).take(300)
                instrumentation.runOnMainSync {
                    val base = instrumentation.targetContext
                    val config = Configuration(base.resources.configuration).apply { fontScale = scale }
                    view = GuidanceOverlayView(base.createConfigurationContext(config))
                    view.guidance = OverlayPresentation.Guidance(
                        "com.android.settings", 1, text,
                        NormalizedTarget(0.8, 0.05, 0.95, 0.12), width, height, 0,
                    )
                    view.layout(0, 0, width, height)
                    view.draw(Canvas(bitmap))
                    assertEquals(text, view.bodyLayout!!.text.toString())
                    assertTrue(view.viewportHeight >= view.bodyLayout!!.getLineBottom(0))
                    view.follow(text.lastIndex)
                }
                SystemClock.sleep(350)
                instrumentation.runOnMainSync {
                    assertTrue(view.scrollYText > 0f)
                    val layout = view.bodyLayout!!
                    assertTrue(view.scrollYText + view.viewportHeight >= layout.height - 1f)
                    view.draw(Canvas(bitmap))
                    if (scale == 2f && width == 1080) {
                        instrumentation.targetContext.openFileOutput("guidance-long.png", 0).use {
                            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
                        }
                    }
                    view.follow(0)
                }
                SystemClock.sleep(350)
                instrumentation.runOnMainSync {
                    assertEquals(0f, view.scrollYText, 0.1f)
                    view.resetScroll()
                }
                bitmap.recycle()
            }
        }
    }
}
