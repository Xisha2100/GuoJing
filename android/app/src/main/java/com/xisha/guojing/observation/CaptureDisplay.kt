package com.xisha.guojing.observation

import android.content.Context
import android.hardware.display.DisplayManager
import android.view.Display

/** Read the same display used by takeScreenshot, including from a service context. */
internal fun captureDisplayRotation(context: Context): Int =
    checkNotNull(
        context.getSystemService(DisplayManager::class.java).getDisplay(Display.DEFAULT_DISPLAY),
    ) { "Capture display is unavailable" }.rotation
