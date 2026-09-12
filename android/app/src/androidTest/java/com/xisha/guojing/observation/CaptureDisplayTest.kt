package com.xisha.guojing.observation

import android.hardware.display.DisplayManager
import android.view.Display
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Test

class CaptureDisplayTest {
    @Test
    fun rotation_is_available_from_a_context_without_an_attached_display() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
        val expected = context.getSystemService(DisplayManager::class.java)
            .getDisplay(Display.DEFAULT_DISPLAY).rotation

        assertEquals(expected, captureDisplayRotation(context))
    }
}
