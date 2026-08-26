package com.xisha.guojing.observation

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import com.xisha.guojing.privacy.InMemoryScreenshot
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Test

class MlKitScreenshotOcrProviderTest {
    @Test
    fun bundled_latin_model_reads_text_and_returns_normalized_bounds() = runBlocking {
        val bitmap = Bitmap.createBitmap(1_000, 400, Bitmap.Config.ARGB_8888)
        val bytes = try {
            Canvas(bitmap).apply {
                drawColor(Color.WHITE)
                drawText(
                    "HELP 123",
                    80f,
                    220f,
                    Paint(Paint.ANTI_ALIAS_FLAG).apply {
                        color = Color.BLACK
                        textSize = 96f
                        typeface = Typeface.DEFAULT_BOLD
                    },
                )
            }
            ByteArrayOutputStream().use { output ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
                output.toByteArray()
            }
        } finally {
            bitmap.recycle()
        }
        val source = InMemoryScreenshot(
            encodedBytes = bytes,
            width = 1_000,
            height = 400,
            sha256 = "0".repeat(64),
        )
        val provider = MlKitScreenshotOcrProvider()
        try {
            val blocks = provider.recognize(source)
            assertTrue(
                "Expected OCR to find the drawn Latin text, got $blocks",
                blocks.any { block ->
                    block.text.replace(" ", "").contains("HELP", ignoreCase = true)
                },
            )
            assertTrue(blocks.any { block -> block.normalizedBounds != null })
        } finally {
            provider.close()
            source.erase()
        }
    }
}
