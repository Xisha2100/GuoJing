package com.xisha.guojing.observation

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Rect
import com.google.android.gms.tasks.Task
import com.google.mlkit.vision.text.Text
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.xisha.guojing.privacy.InMemoryScreenshot
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.max
import kotlin.math.min
import kotlinx.coroutines.suspendCancellableCoroutine

/**
 * Local ML Kit adapter. It receives only the session-owned sanitized/in-memory screenshot
 * supplied by the caller and returns ephemeral OCR blocks for [OcrObservationBuilder].
 */
class MlKitScreenshotOcrProvider : ScreenshotOcrProvider {
    private val recognizers = listOf(
        TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build()),
        TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS),
    )

    override suspend fun recognize(source: InMemoryScreenshot): List<OcrTextBlock> {
        val bitmap = BitmapFactory.decodeByteArray(
            source.encodedBytes,
            0,
            source.encodedBytes.size,
        ) ?: throw IllegalArgumentException("the screenshot bytes are not decodable")
        return try {
            require(bitmap.width > 0 && bitmap.height > 0)
            val image = com.google.mlkit.vision.common.InputImage.fromBitmap(bitmap, 0)
            recognizers
                .map { recognizer -> recognizer.process(image).awaitResult() }
                .flatMap { result -> result.textBlocks.flatMap(Text.TextBlock::getLines) }
                .mapNotNull { line -> line.toOcrTextBlock(bitmap.width, bitmap.height) }
                .distinctBy { block ->
                    listOf(
                        normalize(block.text),
                        block.normalizedBounds?.left,
                        block.normalizedBounds?.top,
                        block.normalizedBounds?.right,
                        block.normalizedBounds?.bottom,
                    )
                }
        } finally {
            bitmap.recycle()
        }
    }

    override fun close() {
        recognizers.forEach { recognizer -> recognizer.close() }
    }
}

interface ScreenshotOcrProvider : AutoCloseable {
    suspend fun recognize(source: InMemoryScreenshot): List<OcrTextBlock>

    override fun close()
}

object DisabledScreenshotOcrProvider : ScreenshotOcrProvider {
    override suspend fun recognize(source: InMemoryScreenshot): List<OcrTextBlock> = emptyList()

    override fun close() = Unit
}

private fun Text.Line.toOcrTextBlock(width: Int, height: Int): OcrTextBlock? {
    val value = text.trim()
    val bounds = boundingBox ?: return null
    if (value.isBlank()) return null
    val normalized = bounds.normalize(width, height) ?: return null
    return OcrTextBlock(
        text = value,
        confidence = confidence.coerceIn(0f, 1f).toDouble(),
        normalizedBounds = normalized,
    )
}

private fun Rect.normalize(width: Int, height: Int): NormalizedScreenBounds? {
    val left = max(0, min(left, width))
    val top = max(0, min(top, height))
    val right = max(0, min(right, width))
    val bottom = max(0, min(bottom, height))
    if (left >= right || top >= bottom) return null
    return NormalizedScreenBounds(
        left = left.toDouble() / width,
        top = top.toDouble() / height,
        right = right.toDouble() / width,
        bottom = bottom.toDouble() / height,
    )
}

private fun normalize(value: String): String = value
    .trim()
    .lowercase()
    .filter { it.isLetterOrDigit() }

private suspend fun <T> Task<T>.awaitResult(): T = suspendCancellableCoroutine { continuation ->
    addOnSuccessListener { result ->
        if (continuation.isActive) continuation.resume(result)
    }
    addOnFailureListener { error ->
        if (continuation.isActive) continuation.resumeWithException(error)
    }
    addOnCanceledListener {
        continuation.cancel()
    }
}
