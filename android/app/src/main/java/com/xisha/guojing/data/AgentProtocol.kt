package com.xisha.guojing.data

import com.xisha.guojing.model.AgentProtocolException
import com.xisha.guojing.model.AgentRunAccepted
import com.xisha.guojing.model.AgentRunSnapshot
import com.xisha.guojing.model.AgentRunStatus
import com.xisha.guojing.model.AgentSessionHandle
import com.xisha.guojing.model.GuidanceDecision
import com.xisha.guojing.model.GuidanceStatus
import com.xisha.guojing.model.NormalizedTarget
import java.util.UUID
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

internal object AgentProtocol {
    private val json = Json

    fun createSessionBody(clientSessionId: UUID, goal: String, targetPackage: String): String =
        buildJsonObject {
            put("schema_version", "1.0")
            put("client_session_id", clientSessionId.toString())
            put("goal", goal)
            put("target_package", targetPackage)
        }.toString()

    fun parseSession(value: String): AgentSessionHandle {
        val root = objectRoot(value)
        requireShape(
            root,
            required = setOf("schema_version", "session_id", "access_token", "status"),
        )
        requireVersion(root)
        if (root.string("status") != "active") fail()
        return AgentSessionHandle(
            sessionId = root.uuid("session_id"),
            accessToken = root.string("access_token").also { if (it.isBlank()) fail() },
        )
    }

    fun parseRunAccepted(value: String): AgentRunAccepted {
        val root = objectRoot(value)
        requireShape(
            root,
            required = setOf("schema_version", "run_id", "status", "events_endpoint"),
        )
        requireVersion(root)
        return AgentRunAccepted(
            runId = root.uuid("run_id"),
            status = AgentRunStatus.parse(root.string("status")),
            eventsEndpoint = root.string("events_endpoint"),
        )
    }

    fun parseRun(value: String): AgentRunSnapshot {
        val root = objectRoot(value)
        requireShape(
            root,
            required = setOf(
                "schema_version",
                "run_id",
                "session_id",
                "status",
                "result",
                "error_code",
                "retryable",
            ),
        )
        requireVersion(root)
        val snapshot = AgentRunSnapshot(
            runId = root.uuid("run_id"),
            sessionId = root.uuid("session_id"),
            status = AgentRunStatus.parse(root.string("status")),
            result = root.objectOrNull("result")?.let(::parseDecision),
            errorCode = root.stringOrNull("error_code"),
            retryable = root.boolean("retryable"),
        )
        val valid = when (snapshot.status) {
            AgentRunStatus.Queued,
            AgentRunStatus.Running,
            -> snapshot.result == null && snapshot.errorCode == null && !snapshot.retryable

            AgentRunStatus.Completed ->
                snapshot.result != null && snapshot.errorCode == null && !snapshot.retryable

            AgentRunStatus.Failed -> snapshot.result == null && snapshot.errorCode != null
            AgentRunStatus.Cancelled ->
                snapshot.result == null && snapshot.errorCode == "cancelled" && !snapshot.retryable
        }
        if (!valid) fail()
        return snapshot
    }

    private fun parseDecision(root: JsonObject): GuidanceDecision {
        requireShape(
            root,
            required = setOf("status", "instruction", "target", "confidence"),
        )
        val status = GuidanceStatus.parse(root.string("status"))
        val instruction = root.stringOrNull("instruction")
        val target = root.objectOrNull("target")?.let(::parseTarget)
        return try {
            GuidanceDecision(
                status = status,
                instruction = instruction,
                target = target,
                confidence = root.number("confidence"),
            )
        } catch (_: IllegalArgumentException) {
            fail()
        }
    }

    private fun parseTarget(root: JsonObject): NormalizedTarget {
        requireShape(root, required = setOf("left", "top", "right", "bottom"))
        return try {
            NormalizedTarget(
                left = root.number("left"),
                top = root.number("top"),
                right = root.number("right"),
                bottom = root.number("bottom"),
            )
        } catch (_: IllegalArgumentException) {
            fail()
        }
    }

    private fun objectRoot(value: String): JsonObject = try {
        json.parseToJsonElement(value).jsonObject
    } catch (_: Exception) {
        fail()
    }

    private fun requireVersion(root: JsonObject) {
        if (root.string("schema_version") != "1.0") fail()
    }

    private fun requireShape(root: JsonObject, required: Set<String>) {
        if (root.keys != required) fail()
    }

    private fun JsonObject.string(name: String): String {
        val primitive = this[name]?.jsonPrimitive ?: fail()
        if (!primitive.isString) fail()
        return primitive.contentOrNull ?: fail()
    }

    private fun JsonObject.stringOrNull(name: String): String? {
        val element = this[name] ?: fail()
        if (element is JsonNull) return null
        val primitive = element.jsonPrimitive
        if (!primitive.isString) fail()
        return primitive.contentOrNull ?: fail()
    }

    private fun JsonObject.objectOrNull(name: String): JsonObject? {
        val element = this[name] ?: fail()
        return if (element is JsonNull) null else try {
            element.jsonObject
        } catch (_: Exception) {
            fail()
        }
    }

    private fun JsonObject.uuid(name: String): UUID = try {
        UUID.fromString(string(name))
    } catch (_: IllegalArgumentException) {
        fail()
    }

    private fun JsonObject.number(name: String): Double = try {
        val primitive = this[name]?.jsonPrimitive ?: fail()
        if (primitive.isString) fail()
        primitive.double
    } catch (_: Exception) {
        fail()
    }

    private fun JsonObject.boolean(name: String): Boolean {
        val primitive = this[name]?.jsonPrimitive ?: fail()
        if (primitive.isString) fail()
        return primitive.booleanOrNull ?: fail()
    }

    private fun fail(): Nothing = throw AgentProtocolException("Invalid agent response")
}
