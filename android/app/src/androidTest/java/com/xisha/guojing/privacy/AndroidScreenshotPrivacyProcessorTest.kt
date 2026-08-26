package com.xisha.guojing.privacy

import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Environment
import android.provider.MediaStore
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream

class AndroidScreenshotPrivacyProcessorTest {
    @Test
    fun import_reads_a_content_uri_and_creates_a_bounded_in_memory_copy() = runBlocking {
        val resolver = InstrumentationRegistry.getInstrumentation().targetContext.contentResolver
        val uri = requireNotNull(
            resolver.insert(
                MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, "guojing-import-test.png")
                    put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                    put(
                        MediaStore.Images.Media.RELATIVE_PATH,
                        "${Environment.DIRECTORY_PICTURES}/GuoJingTests",
                    )
                    put(MediaStore.Images.Media.IS_PENDING, 1)
                },
            ),
        )
        try {
            val bitmap = Bitmap.createBitmap(1_600, 800, Bitmap.Config.ARGB_8888).apply {
                eraseColor(Color.WHITE)
            }
            resolver.openOutputStream(uri)?.use { output ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
            }
            bitmap.recycle()
            resolver.update(
                uri,
                ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) },
                null,
                null,
            )

            val imported = AndroidScreenshotPrivacyProcessor(resolver)
                .importFromPicker(uri.toString())

            assertEquals(1_440, imported.width)
            assertEquals(720, imported.height)
            assertEquals(64, imported.sha256.length)
            imported.erase()
        } finally {
            resolver.delete(uri, null, null)
        }
    }

    @Test
    fun sanitize_replaces_selected_pixels_with_an_opaque_black_mask() = runBlocking {
        val sourceBitmap = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888).apply {
            eraseColor(Color.WHITE)
        }
        val sourceBytes = ByteArrayOutputStream().use { output ->
            sourceBitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
            output.toByteArray()
        }
        sourceBitmap.recycle()
        val source = InMemoryScreenshot(
            encodedBytes = sourceBytes,
            width = 100,
            height = 100,
            sha256 = "a".repeat(64),
        )
        val redaction = requireNotNull(
            NormalizedRedaction.fromDrag(0.2f, 0.2f, 0.8f, 0.8f),
        )
        val processor = AndroidScreenshotPrivacyProcessor(
            InstrumentationRegistry.getInstrumentation().targetContext.contentResolver,
        )

        val sanitized = processor.sanitize(source, listOf(redaction))
        val result = BitmapFactory.decodeByteArray(
            sanitized.encodedBytes,
            0,
            sanitized.encodedBytes.size,
        )

        assertTrue(Color.red(result.getPixel(50, 50)) < 10)
        assertTrue(Color.green(result.getPixel(50, 50)) < 10)
        assertTrue(Color.blue(result.getPixel(50, 50)) < 10)
        assertTrue(Color.red(result.getPixel(5, 5)) > 245)
        assertTrue(Color.green(result.getPixel(5, 5)) > 245)
        assertTrue(Color.blue(result.getPixel(5, 5)) > 245)
        result.recycle()
        sanitized.erase()
        source.erase()
    }
}
