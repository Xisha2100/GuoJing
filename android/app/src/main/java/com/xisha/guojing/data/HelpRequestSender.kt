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

    ;

    companion object {
        fun fromWire(value: String): HelpRequestIntent =
            entries.firstOrNull { it.wireValue == value }
                ?: throw HelpRequestFormatException("Unknown help request intent '$value'")
    }
}

data class HelpRequestSubmission(
    val screenshot: InMemoryScreenshot,
    val question: String,
    val receipt: ScreenshotSanitizationReceipt,
    val intent: HelpRequestIntent,
    /** Stable across transport retries for one user-confirmed submission. */
    val clientRequestId: String = UUID.randomUUID().toString(),
)

data class HelpRequestReceipt(
    val requestId: String,
    val clientRequestId: String,
    val intent: HelpRequestIntent,
    val processingRoute: String,
    val processingStatus: HelpRequestProcessingStatus,
    val statusEndpoint: String,
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
        val clientRequestId = submission.clientRequestId.trim()
        requireUuid(clientRequestId, "client_request_id")
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
        return parseReceipt(
            payload = client.postJson("api/v1/help-requests", body.toString()),
            json = json,
            expectedClientRequestId = clientRequestId,
            expectedIntent = submission.intent,
        )
    }

    private fun parseReceipt(
        payload: String,
        json: Json,
        expectedClientRequestId: String,
        expectedIntent: HelpRequestIntent,
    ): HelpRequestReceipt = try {
        val root = json.parseToJsonElement(payload) as? JsonObject
            ?: throw HelpRequestFormatException("Help request receipt must be a JSON object")
        val schemaVersion = root.requiredString("schema_version")
        if (schemaVersion != "1.1") {
            throw HelpRequestFormatException(
                "Unsupported help request receipt schema '$schemaVersion'",
            )
        }
        val requestId = root.requiredString("request_id")
        requireUuid(requestId, "request_id")
        val clientRequestId = root.requiredString("client_request_id")
        requireUuid(clientRequestId, "client_request_id")
        if (UUID.fromString(clientRequestId) != UUID.fromString(expectedClientRequestId)) {
            throw HelpRequestFormatException("Help request receipt client id does not match submission")
        }
        val intent = HelpRequestIntent.fromWire(root.requiredString("intent"))
        if (intent != expectedIntent) {
            throw HelpRequestFormatException("Help request receipt intent does not match submission")
        }
        val route = root.requiredString("processing_route")
        val expectedRoute = when (intent) {
            HelpRequestIntent.RECORDED_TUTORIAL -> "tutorial_match"
            HelpRequestIntent.GENERAL_GUIDANCE -> "general_guidance"
        }
        if (route != expectedRoute) {
            throw HelpRequestFormatException("Help request receipt route does not match intent")
        }
        val status = HelpRequestProcessingStatus.fromWire(
            root.requiredString("processing_status"),
        )
        if (status != HelpRequestProcessingStatus.RECEIVED) {
            throw HelpRequestFormatException("Help request submission receipt must be received")
        }
        val statusEndpoint = root.requiredString("status_endpoint")
        val expectedEndpoint = "/api/v1/help-requests/$requestId"
        if (statusEndpoint != expectedEndpoint) {
            throw HelpRequestFormatException("Help request receipt status endpoint does not match request")
        }
        HelpRequestReceipt(
            requestId = requestId,
            clientRequestId = clientRequestId,
            intent = intent,
            processingRoute = route,
            processingStatus = status,
            statusEndpoint = statusEndpoint,
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

    private fun requireUuid(value: String, field: String) {
        try {
            UUID.fromString(value)
        } catch (error: IllegalArgumentException) {
            throw HelpRequestFormatException("Help request '$field' is not a UUID", error)
        }
    }
}
