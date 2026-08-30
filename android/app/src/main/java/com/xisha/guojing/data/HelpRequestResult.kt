package com.xisha.guojing.data

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.jsonPrimitive

enum class HelpRequestProcessingStatus(val wireValue: String) {
    RECEIVED("received"),
    PROCESSING("processing"),
    NEEDS_HUMAN_REVIEW("needs_human_review"),
    GUIDANCE_READY("guidance_ready"),
    ;

    companion object {
        fun fromWire(value: String): HelpRequestProcessingStatus =
            entries.firstOrNull { it.wireValue == value }
                ?: throw HelpRequestFormatException(
                    "Unknown help request processing status '$value'",
                )
    }
}

data class HelpRequestGuidanceStep(
    val stepId: String,
    val title: String,
    val instruction: String,
)

data class HelpRequestGuidance(
    val title: String,
    val steps: List<HelpRequestGuidanceStep>,
)

data class HelpRequestResult(
    val requestId: String,
    val clientRequestId: String,
    val intent: HelpRequestIntent,
    val processingRoute: String,
    val processingStatus: HelpRequestProcessingStatus,
    val receivedAt: String,
    val updatedAt: String,
    val guidance: HelpRequestGuidance? = null,
    val humanReviewReason: String? = null,
)

fun interface HelpRequestStatusReader {
    suspend fun fetch(requestId: String): HelpRequestResult
}

object DisabledHelpRequestStatusReader : HelpRequestStatusReader {
    override suspend fun fetch(requestId: String): HelpRequestResult =
        error("Help request status querying is not configured")
}

class HttpHelpRequestStatusReader internal constructor(
    private val client: HttpJsonClient,
    private val json: Json = Json,
) : HelpRequestStatusReader {
    constructor(baseUrl: String) : this(HttpJsonClient(baseUrl))

    override suspend fun fetch(requestId: String): HelpRequestResult {
        val normalizedRequestId = requestId.trim()
        requireUuid(normalizedRequestId)
        val result = parseResult(
            client.get("api/v1/help-requests/$normalizedRequestId"),
            json,
        )
        if (result.requestId != normalizedRequestId) {
            throw HelpRequestFormatException("Help request result id does not match the requested id")
        }
        return result
    }

    private fun parseResult(payload: String, json: Json): HelpRequestResult = try {
        val root = json.parseToJsonElement(payload) as? JsonObject
            ?: throw HelpRequestFormatException("Help request result must be a JSON object")
        val schemaVersion = root.requiredString("schema_version")
        if (schemaVersion != "1.1") {
            throw HelpRequestFormatException(
                "Unsupported help request result schema '$schemaVersion'",
            )
        }
        val processingStatus = HelpRequestProcessingStatus.fromWire(
            root.requiredString("processing_status"),
        )
        val guidance = root.optionalGuidance(json)
        val humanReviewReason = root.optionalString("human_review_reason")
        if (processingStatus == HelpRequestProcessingStatus.GUIDANCE_READY && guidance == null) {
            throw HelpRequestFormatException(
                "guidance_ready results must include guidance",
            )
        }
        if (processingStatus != HelpRequestProcessingStatus.GUIDANCE_READY && guidance != null) {
            throw HelpRequestFormatException(
                "guidance is only allowed when guidance is ready",
            )
        }
        if (processingStatus == HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW &&
            humanReviewReason.isNullOrBlank()
        ) {
            throw HelpRequestFormatException(
                "human review results need a non-empty reason",
            )
        }
        if (processingStatus != HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW &&
            humanReviewReason != null
        ) {
            throw HelpRequestFormatException(
                "a review reason is only allowed during human review",
            )
        }
        val intent = HelpRequestIntent.fromWire(root.requiredString("intent"))
        val processingRoute = root.requiredString("processing_route")
        val expectedRoute = when (intent) {
            HelpRequestIntent.RECORDED_TUTORIAL -> "tutorial_match"
            HelpRequestIntent.GENERAL_GUIDANCE -> "general_guidance"
        }
        if (processingRoute != expectedRoute) {
            throw HelpRequestFormatException("Help request result route does not match intent")
        }
        return HelpRequestResult(
            requestId = root.requiredUuidString("request_id"),
            clientRequestId = root.requiredUuidString("client_request_id"),
            intent = intent,
            processingRoute = processingRoute,
            processingStatus = processingStatus,
            receivedAt = root.requiredString("received_at"),
            updatedAt = root.requiredString("updated_at"),
            guidance = guidance,
            humanReviewReason = humanReviewReason,
        )
    } catch (error: HelpRequestFormatException) {
        throw error
    } catch (error: IllegalArgumentException) {
        throw HelpRequestFormatException("Help request result contains invalid JSON", error)
    }

    private fun JsonObject.optionalGuidance(json: Json): HelpRequestGuidance? {
        val value = this["guidance"]
        if (value == null || value is JsonNull) return null
        val guidance = value as? JsonObject
            ?: throw HelpRequestFormatException("Help request guidance must be an object")
        val steps = guidance["steps"] as? JsonArray
            ?: throw HelpRequestFormatException("Help request guidance has no steps array")
        if (steps.isEmpty() || steps.size > 20) {
            throw HelpRequestFormatException("Help request guidance must contain 1 to 20 steps")
        }
        return HelpRequestGuidance(
            title = guidance.requiredSafeText("title"),
            steps = steps.mapIndexed { index, stepValue ->
                val step = stepValue as? JsonObject
                    ?: throw HelpRequestFormatException(
                        "Help request guidance step $index must be an object",
                    )
                if (step["requires_manual_action"]?.jsonPrimitive?.content != "true") {
                    throw HelpRequestFormatException(
                        "Help request guidance step $index must require manual action",
                    )
                }
                HelpRequestGuidanceStep(
                    stepId = step.requiredString("step_id"),
                    title = step.requiredSafeText("title"),
                    instruction = step.requiredSafeInstruction(),
                )
            },
        )
    }

    private fun JsonObject.optionalString(name: String): String? {
        val value = this[name]
        if (value == null || value is JsonNull) return null
        return value.jsonPrimitive.content.takeIf { it.isNotBlank() }
    }

    private fun JsonObject.requiredString(name: String): String {
        val value = this[name]?.jsonPrimitive?.content
        if (value.isNullOrBlank()) {
            throw HelpRequestFormatException("Help request result has no non-empty '$name'")
        }
        return value
    }

    private fun JsonObject.requiredUuidString(name: String): String {
        val value = requiredString(name)
        requireUuid(value)
        return value
    }

    private fun JsonObject.requiredSafeInstruction(): String {
        val value = requiredString("instruction")
        requireSafeGuidanceText(value)
        return value
    }

    private fun JsonObject.requiredSafeText(name: String): String {
        val value = requiredString(name)
        requireSafeGuidanceText(value)
        return value
    }

    private fun requireSafeGuidanceText(value: String) {
        val normalized = value
            .lowercase()
            .filter { it.isLetterOrDigit() }
        if (UNSAFE_GUIDANCE_TERMS.any(normalized::contains)) {
            throw HelpRequestFormatException("Help request guidance contains a blocked operation")
        }
    }

    private fun requireUuid(value: String) {
        try {
            java.util.UUID.fromString(value)
        } catch (error: IllegalArgumentException) {
            throw HelpRequestFormatException("Help request id is not a UUID", error)
        }
    }

    private companion object {
        val UNSAFE_GUIDANCE_TERMS = listOf(
            "转账",
            "汇款",
            "收款",
            "提现",
            "充值",
            "付款",
            "支付",
            "支付密码",
            "发送金额",
            "发红包",
            "删除账号",
            "删除账户",
            "确认删除",
            "注销账号",
            "注销账户",
            "输入密码",
            "输入支付密码",
            "填写密码",
            "填写支付密码",
            "键入密码",
            "键入支付密码",
            "输入验证码",
            "填写验证码",
            "确认购买",
            "立即下单",
            "确认下单",
            "购买",
        )
    }
}
