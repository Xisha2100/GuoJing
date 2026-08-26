package com.xisha.guojing.privacy

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ImageDecoder
import android.graphics.Paint
import android.graphics.RectF
import android.net.Uri
import android.os.Build
import android.util.Log
import com.xisha.guojing.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import kotlin.math.roundToInt

class AndroidScreenshotPrivacyProcessor(
    private val contentResolver: ContentResolver,
) : ScreenshotPrivacyProcessor {
    override suspend fun importFromPicker(uriString: String): InMemoryScreenshot =
        withContext(Dispatchers.IO) {
            var stage = "validate_uri"
            try {
                val uri = Uri.parse(uriString)
                require(uri.scheme == ContentResolver.SCHEME_CONTENT) {
                    "Only content URIs from the system picker are accepted"
                }
                stage = "read_media_type"
                val mediaType = contentResolver.getType(uri)
                require(mediaType == null || mediaType.startsWith("image/")) {
                    "The selected item is not an image"
                }
                stage = "decode_pixels"
                val bitmap = decodePickerBitmap(uri)
                try {
                    stage = "encode_preview"
                    encode(bitmap)
                } finally {
                    bitmap.recycle()
                }
            } catch (error: Exception) {
                if (BuildConfig.DEBUG) {
                    Log.d(
                        LOG_TAG,
                        "picker import failed stage=$stage type=${error.javaClass.simpleName}",
                    )
                }
                throw error
            }
        }

    override suspend fun sanitize(
        source: InMemoryScreenshot,
        redactions: List<NormalizedRedaction>,
    ): InMemoryScreenshot = withContext(Dispatchers.Default) {
        val sourceBitmap = BitmapFactory.decodeByteArray(
            source.encodedBytes,
            0,
            source.encodedBytes.size,
        ) ?: error("Unable to decode the in-memory screenshot")
        val sanitizedBitmap = Bitmap.createBitmap(
            sourceBitmap.width,
            sourceBitmap.height,
            Bitmap.Config.ARGB_8888,
        )
        try {
            val canvas = Canvas(sanitizedBitmap)
            canvas.drawColor(Color.WHITE)
            canvas.drawBitmap(sourceBitmap, 0f, 0f, null)
            val maskPaint = Paint().apply {
                color = Color.BLACK
                style = Paint.Style.FILL
                isAntiAlias = false
            }
            redactions.forEach { redaction ->
                canvas.drawRect(
                    RectF(
                        redaction.left * sanitizedBitmap.width,
                        redaction.top * sanitizedBitmap.height,
                        redaction.right * sanitizedBitmap.width,
                        redaction.bottom * sanitizedBitmap.height,
                    ),
                    maskPaint,
                )
            }
            encode(sanitizedBitmap)
        } finally {
            sourceBitmap.recycle()
            sanitizedBitmap.recycle()
        }
    }

    private fun decodePickerBitmap(uri: Uri): Bitmap =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(contentResolver, uri)) {
                    decoder,
                    info,
                    _,
                ->
                val largestDimension = maxOf(info.size.width, info.size.height)
                if (largestDimension > MAX_DIMENSION) {
                    val scale = MAX_DIMENSION.toFloat() / largestDimension
                    decoder.setTargetSize(
                        (info.size.width * scale).roundToInt(),
                        (info.size.height * scale).roundToInt(),
                    )
                }
                decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
            }
        } else {
            decodeLegacyBitmap(uri)
        }

    private fun decodeLegacyBitmap(uri: Uri): Bitmap {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        contentResolver.openFileDescriptor(uri, "r")?.use { descriptor ->
            BitmapFactory.decodeFileDescriptor(descriptor.fileDescriptor, null, options)
        } ?: error("Unable to read the selected screenshot")
        require(options.outWidth > 0 && options.outHeight > 0) {
            "The selected image has invalid dimensions"
        }
        val sampleSize = calculateSampleSize(options.outWidth, options.outHeight)
        return contentResolver.openFileDescriptor(uri, "r")?.use { descriptor ->
            BitmapFactory.decodeFileDescriptor(
                descriptor.fileDescriptor,
                null,
                BitmapFactory.Options().apply {
                    inSampleSize = sampleSize
                    inPreferredConfig = Bitmap.Config.ARGB_8888
                },
            )
        } ?: error("Unable to decode the selected screenshot")
    }

    private fun calculateSampleSize(width: Int, height: Int): Int {
        var sampleSize = 1
        while (width / sampleSize > MAX_DIMENSION || height / sampleSize > MAX_DIMENSION) {
            sampleSize *= 2
        }
        return sampleSize
    }

    private fun encode(bitmap: Bitmap): InMemoryScreenshot {
        val bytes = ByteArrayOutputStream().use { output ->
            check(bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, output))
            output.toByteArray()
        }
        require(bytes.size <= MAX_ENCODED_BYTES) {
            "The processed screenshot is too large"
        }
        return InMemoryScreenshot(
            encodedBytes = bytes,
            width = bitmap.width,
            height = bitmap.height,
            sha256 = bytes.sha256(),
        )
    }

    private fun ByteArray.sha256(): String = MessageDigest.getInstance("SHA-256")
        .digest(this)
        .joinToString(separator = "") { byte ->
            "%02x".format(byte.toInt() and 0xff)
        }

    private companion object {
        const val MAX_DIMENSION = 1_440
        const val MAX_ENCODED_BYTES = 8 * 1024 * 1024
        const val JPEG_QUALITY = 92
        const val LOG_TAG = "GuoJingScreenshot"
    }
}
