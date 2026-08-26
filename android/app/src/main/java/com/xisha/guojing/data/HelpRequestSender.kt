package com.xisha.guojing.data

import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.ScreenshotSanitizationReceipt
import java.util.Base64
import java.util.UUID
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

enum class HelpRequestIntent(val wireValue: String) {
    RECORDED_TUTORIAL("recorded_tutorial"),
    GENERAL_GUIDANCE("general_guidance"),
}

data class HelpRequestSubmission(
    val screenshot: InMemoryScreenshot,
    val question: String,
    val receipt: ScreenshotSanitizationReceipt,
    val intent: HelpRequestIntent,
)

data class HelpRequestReceipt(
    val requestId: String,
    val clientRequestId: String,
    val processingRoute: String,
    val processingStatus: String,
)

fun interface HelpRequestSender {
    suspend fun send(submission: HelpRequestSubmission): HelpRequestReceipt
}

object DisabledHelpRequestSender : HelpRequestSender {
    override suspend fun send(submission: HelpRequestSubmission): HelpRequestReceipt =
        error("Help request sending is not configured")
}

class HelpRequestFormatException(
    message: String,
    cause: Throwable? = null,
) : IllegalArgumentException(message, cause)

class HttpHelpRequestSender internal constructor(
    private val client: HttpJsonClient,
    private val json: Json = Json,
) : HelpRequestSender {
    constructor(baseUrl: String) : this(HttpJsonClient(baseUrl))

    override suspend fun send(submission: HelpRequestSubmission): HelpRequestReceipt {
        val clientRequestId = UUID.randomUUID().toString()
        val body = buildJsonObject {
            put("schema_version", "1.0")
            put("client_request_id", clientRequestId)
            put("intent", submission.intent.wireValue)
            put("question", submission.question)
            put("image_media_type", "image/jpeg")
            put("image_width", submission.screenshot.width)
            put("image_height", submission.screenshot.height)
            put("redaction_count", submission.receipt.redactionCount)
            put(
                "no_sensitive_content_confirmed",
                submission.receipt.noSensitiveContentConfirmed,
            )
            put("sanitized_sha256", submission.receipt.sanitizedSha256)
            put("send_consent", true)
            put(
                "sanitized_image_base64",
                Base64.getEncoder().encodeToString(submission.screenshot.encodedBytes),
            )
        }
        return parseReceipt(client.postJson("api/v1/help-requests", body.toString()), json)
    }

    private fun parseReceipt(payload: String, json: Json): HelpRequestReceipt = try {
        val root = json.parseToJsonElement(payload) as? JsonObject
            ?: throw HelpRequestFormatException("Help request receipt must be a JSON object")
        HelpRequestReceipt(
            requestId = root.requiredString("request_id"),
            clientRequestId = root.requiredString("client_request_id"),
            processingRoute = root.requiredString("processing_route"),
            processingStatus = root.requiredString("processing_status"),
        )
    } catch (error: HelpRequestFormatException) {
        throw error
    } catch (error: IllegalArgumentException) {
        throw HelpRequestFormatException("Help request receipt contains invalid JSON", error)
    }

    private fun JsonObject.requiredString(name: String): String {
        val value = this[name]?.jsonPrimitive?.content
        if (value.isNullOrBlank()) {
            throw HelpRequestFormatException("Help request receipt has no non-empty '$name'")
        }
        return value
    }
}
