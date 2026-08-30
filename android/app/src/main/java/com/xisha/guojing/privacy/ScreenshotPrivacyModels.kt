package com.xisha.guojing.privacy

import kotlin.math.max
import kotlin.math.min

@ConsistentCopyVisibility
data class NormalizedRedaction private constructor(
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
) {
    companion object {
        fun fromDrag(
            startX: Float,
            startY: Float,
            endX: Float,
            endY: Float,
            minimumDimension: Float = MINIMUM_DIMENSION,
        ): NormalizedRedaction? {
            val left = min(startX, endX).coerceIn(0f, 1f)
            val top = min(startY, endY).coerceIn(0f, 1f)
            val right = max(startX, endX).coerceIn(0f, 1f)
            val bottom = max(startY, endY).coerceIn(0f, 1f)
            if (right - left < minimumDimension || bottom - top < minimumDimension) {
                return null
            }
            return NormalizedRedaction(left, top, right, bottom)
        }

        private const val MINIMUM_DIMENSION = 0.02f
    }
}

/** Session-owned encoded pixels. Call [erase] as soon as this copy is no longer needed. */
class InMemoryScreenshot(
    val encodedBytes: ByteArray,
    val width: Int,
    val height: Int,
    val sha256: String,
) {
    init {
        require(encodedBytes.isNotEmpty())
        require(width > 0 && height > 0)
        require(sha256.length == 64)
    }

    val byteCount: Int get() = encodedBytes.size

    fun erase() {
        encodedBytes.fill(0)
    }
}

data class ScreenshotSanitizationReceipt(
    val redactionCount: Int,
    val noSensitiveContentConfirmed: Boolean,
    val sanitizedSha256: String,
) {
    init {
        require(redactionCount >= 0)
        require(sanitizedSha256.matches(SHA256_PATTERN))
        // These flags describe mutually exclusive privacy proofs: either the
        // user masked one or more regions, or explicitly confirmed that none
        // were sensitive.  Accepting both would make the receipt ambiguous.
        require(
            (redactionCount == 0 && noSensitiveContentConfirmed) ||
                (redactionCount > 0 && !noSensitiveContentConfirmed),
        )
    }

    private companion object {
        val SHA256_PATTERN = Regex("[0-9a-fA-F]{64}")
    }
}
