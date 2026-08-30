package com.xisha.guojing.data

import com.xisha.guojing.observation.AnchorEvidence
import com.xisha.guojing.observation.NormalizedScreenBounds
import com.xisha.guojing.observation.ObservationEvidenceSource
import com.xisha.guojing.observation.ObservationSharingPolicy
import com.xisha.guojing.observation.ScreenObservation
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/** Sanitized, retry-stable semantic evidence for one accepted help request. */
data class HelpRequestEvidenceSubmission(
    val requestId: String,
    val accessToken: String,
    val evidenceId: String,
    val packageName: String,
    val versionName: String,
    val versionCode: Long,
    val source: EvidenceSource,
    val sharingPolicy: EvidenceSharingPolicy,
    val structureScore: Double,
    val capturedAt: Instant,
    val expiresAt: Instant,
    val anchors: List<HelpRequestEvidenceAnchor>,
) {
    init {
        requireUuid(requestId, "requestId")
        requireUuid(evidenceId, "evidenceId")
        require(accessToken.isNotBlank())
        require(packageName.isNotBlank())
        require(versionName.isNotBlank())
        require(versionCode > 0)
        require(structureScore in 0.0..1.0)
        require(expiresAt.isAfter(capturedAt))
        require(anchors.isNotEmpty())
    }

    companion object {
        /** Never maps local-only observations into a network request. */
        fun fromObservation(
            requestId: String,
            accessToken: String,
            observation: ScreenObservation,
            evidenceId: String = UUID.randomUUID().toString(),
            capturedAt: Instant = Instant.now(),
        ): HelpRequestEvidenceSubmission {
            require(observation.sharingPolicy == ObservationSharingPolicy.SanitizedNetworkAllowed) {
                "Only explicitly sanitized network evidence may be submitted"
            }
            return HelpRequestEvidenceSubmission(
                requestId = requestId,
                accessToken = accessToken,
                evidenceId = evidenceId,
                packageName = observation.app.packageName,
                versionName = observation.app.versionName,
                versionCode = observation.app.versionCode,
                source = EvidenceSource.fromObservation(observation.evidenceSource),
                sharingPolicy = EvidenceSharingPolicy.SanitizedNetworkAllowed,
                structureScore = observation.structureScore,
                capturedAt = capturedAt,
                expiresAt = capturedAt.plus(DEFAULT_EVIDENCE_TTL_MINUTES, ChronoUnit.MINUTES),
                anchors = observation.anchorEvidence.map(HelpRequestEvidenceAnchor::fromObservation),
            )
        }
    }
}

enum class EvidenceSource(val wireValue: String) {
    Accessibility("accessibility"),
    Ocr("ocr"),
    ;

    companion object {
        fun fromObservation(source: ObservationEvidenceSource): EvidenceSource = when (source) {
            ObservationEvidenceSource.Accessibility -> Accessibility
            ObservationEvidenceSource.Ocr -> Ocr
        }
    }
}

enum class EvidenceSharingPolicy(val wireValue: String) {
    SanitizedNetworkAllowed("sanitized_network_allowed"),
}

data class HelpRequestEvidenceAnchor(
    val anchorId: String,
    val confidence: Double,
    val normalizedBounds: EvidenceBounds? = null,
) {
    init {
        require(anchorId.isNotBlank())
        require(confidence in 0.0..1.0)
    }

    companion object {
        fun fromObservation(value: AnchorEvidence): HelpRequestEvidenceAnchor = HelpRequestEvidenceAnchor(
            anchorId = value.anchorId,
            confidence = value.confidence,
            normalizedBounds = value.normalizedBounds?.let(EvidenceBounds::fromObservation),
        )
    }
}

data class EvidenceBounds(
    val left: Double,
    val top: Double,
    val right: Double,
    val bottom: Double,
) {
    init {
        require(left in 0.0..1.0 && top in 0.0..1.0 && right in 0.0..1.0 && bottom in 0.0..1.0)
        require(left < right && top < bottom)
    }

    companion object {
        fun fromObservation(value: NormalizedScreenBounds): EvidenceBounds = EvidenceBounds(
            left = value.left,
            top = value.top,
            right = value.right,
            bottom = value.bottom,
        )
    }
}

fun interface HelpRequestEvidenceSender {
    suspend fun send(submission: HelpRequestEvidenceSubmission): HelpRequestEvidenceSubmission
}

object DisabledHelpRequestEvidenceSender : HelpRequestEvidenceSender {
    override suspend fun send(submission: HelpRequestEvidenceSubmission): HelpRequestEvidenceSubmission =
        error("Help request evidence sending is not configured")
}

class HttpHelpRequestEvidenceSender internal constructor(
    private val client: HttpJsonClient,
    private val json: Json = Json,
) : HelpRequestEvidenceSender {
    constructor(baseUrl: String) : this(HttpJsonClient(baseUrl))

    override suspend fun send(
        submission: HelpRequestEvidenceSubmission,
    ): HelpRequestEvidenceSubmission {
        val payload = buildJsonObject {
            put("schema_version", "1.0")
            put("evidence_id", submission.evidenceId)
            put("package_name", submission.packageName)
            put("version_name", submission.versionName)
            put("version_code", submission.versionCode)
            put("source", submission.source.wireValue)
            put("sharing_policy", submission.sharingPolicy.wireValue)
            put("structure_score", submission.structureScore)
            put("captured_at", submission.capturedAt.toString())
            put("expires_at", submission.expiresAt.toString())
            put("anchors", JsonArray(submission.anchors.map(::anchorJson)))
        }
        return parseResponse(
            requestId = submission.requestId,
            expectedEvidenceId = submission.evidenceId,
            accessToken = submission.accessToken,
            payload = client.postJson(
                "api/v1/help-requests/${submission.requestId}/evidence",
                payload.toString(),
                headers = mapOf("X-Help-Request-Token" to submission.accessToken),
            ),
        )
    }

    private fun anchorJson(anchor: HelpRequestEvidenceAnchor): JsonObject = buildJsonObject {
        put("anchor_id", anchor.anchorId)
        put("confidence", anchor.confidence)
        anchor.normalizedBounds?.let { bounds ->
            put("normalized_bounds", buildJsonObject {
                put("left", bounds.left)
                put("top", bounds.top)
                put("right", bounds.right)
                put("bottom", bounds.bottom)
            })
        }
    }

    private fun parseResponse(
        requestId: String,
        expectedEvidenceId: String,
        accessToken: String,
        payload: String,
    ): HelpRequestEvidenceSubmission = try {
        val root = json.parseToJsonElement(payload) as? JsonObject
            ?: throw HelpRequestFormatException("Help request evidence response must be a JSON object")
        if (root.requiredString("schema_version") != "1.0") {
            throw HelpRequestFormatException("Unsupported help request evidence schema")
        }
        val responseRequestId = root.requiredString("request_id")
        val responseEvidenceId = root.requiredString("evidence_id")
        if (responseRequestId != requestId || responseEvidenceId != expectedEvidenceId) {
            throw HelpRequestFormatException("Help request evidence response does not match submission")
        }
        HelpRequestEvidenceSubmission(
            requestId = responseRequestId,
            accessToken = accessToken,
            evidenceId = responseEvidenceId,
            packageName = root.requiredString("package_name"),
            versionName = root.requiredString("version_name"),
            versionCode = root.requiredLong("version_code"),
            source = EvidenceSource.entries.firstOrNull {
                it.wireValue == root.requiredString("source")
            } ?: throw HelpRequestFormatException("Unknown evidence source"),
            sharingPolicy = EvidenceSharingPolicy.SanitizedNetworkAllowed.takeIf {
                root.requiredString("sharing_policy") == it.wireValue
            } ?: throw HelpRequestFormatException("Evidence response must remain sanitized_network_allowed"),
            structureScore = root.requiredDouble("structure_score"),
            capturedAt = Instant.parse(root.requiredString("captured_at")),
            expiresAt = Instant.parse(root.requiredString("expires_at")),
            anchors = root.requiredAnchors(),
        )
    } catch (error: HelpRequestFormatException) {
        throw error
    } catch (error: Exception) {
        throw HelpRequestFormatException("Help request evidence response contains invalid JSON", error)
    }

    private fun JsonObject.requiredAnchors(): List<HelpRequestEvidenceAnchor> {
        val raw = this["anchors"] as? JsonArray
            ?: throw HelpRequestFormatException("Help request evidence response has no anchors")
        return raw.map { element ->
            val anchor = element as? JsonObject
                ?: throw HelpRequestFormatException("Help request evidence anchor must be an object")
            HelpRequestEvidenceAnchor(
                anchorId = anchor.requiredString("anchor_id"),
                confidence = anchor.requiredDouble("confidence"),
            )
        }
    }

    private fun JsonObject.requiredString(name: String): String = this[name]?.jsonPrimitive?.content
        ?.takeIf(String::isNotBlank)
        ?: throw HelpRequestFormatException("Help request evidence has no non-empty '$name'")

    private fun JsonObject.requiredLong(name: String): Long = requiredString(name).toLongOrNull()
        ?: throw HelpRequestFormatException("Help request evidence '$name' must be a number")

    private fun JsonObject.requiredDouble(name: String): Double = requiredString(name).toDoubleOrNull()
        ?.takeIf { it in 0.0..1.0 }
        ?: throw HelpRequestFormatException("Help request evidence '$name' must be a normalized number")
}

private fun requireUuid(value: String, field: String) {
    try {
        UUID.fromString(value)
    } catch (error: IllegalArgumentException) {
        throw HelpRequestFormatException("Help request evidence '$field' is not a UUID", error)
    }
}

private const val DEFAULT_EVIDENCE_TTL_MINUTES = 10L
