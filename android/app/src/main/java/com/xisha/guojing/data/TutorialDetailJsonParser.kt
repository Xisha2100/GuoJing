package com.xisha.guojing.data

import com.xisha.guojing.model.ActionKind
import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.model.AppIdentity
import com.xisha.guojing.model.NormalizedBounds
import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.PublishedTutorialDetail
import com.xisha.guojing.model.RelativeConstraint
import com.xisha.guojing.model.RelativePosition
import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.model.ScreenAnchor
import com.xisha.guojing.model.SemanticLocator
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.model.TutorialNode
import com.xisha.guojing.model.TutorialTransition
import com.xisha.guojing.model.VerificationStatus
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive

class TutorialDetailFormatException(
    message: String,
    cause: Throwable? = null,
) : IllegalArgumentException(message, cause)

internal class TutorialDetailJsonParser(
    private val json: Json = Json,
) {
    fun parse(payload: String): PublishedTutorialDetail = try {
        val root = json.parseToJsonElement(payload).requiredObject("response")
        val graphObject = root.requiredObject("graph", "response")
        val graph = parseGraph(graphObject)
        validateGraph(graph)
        PublishedTutorialDetail(
            revisionNumber = root.requiredInt("revision_number", "response"),
            publishedAt = root.requiredString("published_at", "response"),
            graph = graph,
        )
    } catch (error: TutorialDetailFormatException) {
        throw error
    } catch (error: IllegalArgumentException) {
        throw TutorialDetailFormatException("Tutorial detail contains invalid JSON", error)
    }

    private fun parseGraph(value: JsonObject): TutorialGraph {
        val schemaVersion = value.requiredString("schema_version", "graph")
        if (schemaVersion != SUPPORTED_SCHEMA_VERSION) {
            throw TutorialDetailFormatException(
                "Unsupported tutorial schema version '$schemaVersion'",
            )
        }
        return TutorialGraph(
            schemaVersion = schemaVersion,
            graphId = value.requiredString("graph_id", "graph"),
            title = value.requiredString("title", "graph"),
            recordedApp = parseApp(value.requiredObject("recorded_app", "graph")),
            startNodeId = value.requiredString("start_node_id", "graph"),
            nodes = value.requiredArray("nodes", "graph").mapIndexed(::parseNode),
            transitions = value.requiredArray("transitions", "graph")
                .mapIndexed(::parseTransition),
        )
    }

    private fun parseApp(value: JsonObject): AppIdentity = AppIdentity(
        packageName = value.requiredString("package_name", "recorded_app"),
        versionName = value.requiredString("version_name", "recorded_app"),
        versionCode = value.requiredInt("version_code", "recorded_app"),
    )

    private fun parseNode(index: Int, element: kotlinx.serialization.json.JsonElement): TutorialNode {
        val context = "node[$index]"
        val value = element.requiredObject(context)
        return TutorialNode(
            nodeId = value.requiredString("node_id", context),
            title = value.requiredString("title", context),
            anchors = value.requiredArray("anchors", context).mapIndexed { anchorIndex, anchor ->
                parseAnchor(anchorIndex, anchor, context)
            },
            privacyMode = value.requiredEnum("privacy_mode", context, PrivacyMode.entries) {
                it.wireName
            },
            verificationStatus = value.requiredEnum(
                "verification_status",
                context,
                VerificationStatus.entries,
            ) { it.wireName },
            lastVerifiedVersionCode = value.optionalInt("last_verified_version_code", context),
        )
    }

    private fun parseAnchor(
        index: Int,
        element: kotlinx.serialization.json.JsonElement,
        nodeContext: String,
    ): ScreenAnchor {
        val context = "$nodeContext.anchor[$index]"
        val value = element.requiredObject(context)
        return ScreenAnchor(
            anchorId = value.requiredString("anchor_id", context),
            role = value.requiredEnum("role", context, AnchorRole.entries) { it.wireName },
            locator = parseLocator(value.requiredObject("locator", context), context),
            relativeConstraints = value.requiredArray("relative_constraints", context)
                .mapIndexed { constraintIndex, constraint ->
                    parseRelativeConstraint(constraintIndex, constraint, context)
                },
            boundsFallback = value.optionalObject("bounds_fallback", context)?.let(::parseBounds),
        )
    }

    private fun parseLocator(value: JsonObject, parent: String): SemanticLocator {
        val context = "$parent.locator"
        val locator = SemanticLocator(
            resourceId = value.optionalString("resource_id", context),
            contentDescription = value.optionalString("content_description", context),
            text = value.optionalString("text", context),
            ocrText = value.optionalString("ocr_text", context),
        )
        if (
            listOf(
                locator.resourceId,
                locator.contentDescription,
                locator.text,
                locator.ocrText,
            ).none { !it.isNullOrBlank() }
        ) {
            throw TutorialDetailFormatException("$context has no semantic value")
        }
        return locator
    }

    private fun parseRelativeConstraint(
        index: Int,
        element: kotlinx.serialization.json.JsonElement,
        anchorContext: String,
    ): RelativeConstraint {
        val context = "$anchorContext.relative_constraint[$index]"
        val value = element.requiredObject(context)
        return RelativeConstraint(
            referenceAnchorId = value.requiredString("reference_anchor_id", context),
            position = value.requiredEnum(
                "position",
                context,
                RelativePosition.entries,
            ) { it.wireName },
        )
    }

    private fun parseBounds(value: JsonObject): NormalizedBounds {
        val bounds = NormalizedBounds(
            left = value.requiredDouble("left", "bounds_fallback"),
            top = value.requiredDouble("top", "bounds_fallback"),
            right = value.requiredDouble("right", "bounds_fallback"),
            bottom = value.requiredDouble("bottom", "bounds_fallback"),
        )
        if (
            bounds.left !in 0.0..1.0 || bounds.top !in 0.0..1.0 ||
            bounds.right !in 0.0..1.0 || bounds.bottom !in 0.0..1.0 ||
            bounds.left >= bounds.right || bounds.top >= bounds.bottom
        ) {
            throw TutorialDetailFormatException("bounds_fallback is not a normalized rectangle")
        }
        return bounds
    }

    private fun parseTransition(
        index: Int,
        element: kotlinx.serialization.json.JsonElement,
    ): TutorialTransition {
        val context = "transition[$index]"
        val value = element.requiredObject(context)
        return TutorialTransition(
            transitionId = value.requiredString("transition_id", context),
            sourceNodeId = value.requiredString("source_node_id", context),
            targetNodeId = value.requiredString("target_node_id", context),
            actionKind = value.requiredEnum("action_kind", context, ActionKind.entries) {
                it.wireName
            },
            instruction = value.requiredString("instruction", context),
            riskLevel = value.requiredEnum("risk_level", context, RiskLevel.entries) {
                it.wireName
            },
            targetAnchorId = value.optionalString("target_anchor_id", context),
        )
    }

    private fun validateGraph(graph: TutorialGraph) {
        val nodeIds = graph.nodes.map { it.nodeId }
        if (nodeIds.size != nodeIds.toSet().size) {
            throw TutorialDetailFormatException("Tutorial graph contains duplicate node ids")
        }
        if (graph.startNodeId !in nodeIds) {
            throw TutorialDetailFormatException("Tutorial graph start node does not exist")
        }
        val transitionIds = graph.transitions.map { it.transitionId }
        if (transitionIds.size != transitionIds.toSet().size) {
            throw TutorialDetailFormatException("Tutorial graph contains duplicate transition ids")
        }
        graph.transitions.forEach { transition ->
            if (transition.sourceNodeId !in nodeIds || transition.targetNodeId !in nodeIds) {
                throw TutorialDetailFormatException(
                    "Transition '${transition.transitionId}' references an unknown node",
                )
            }
        }
    }

    private fun kotlinx.serialization.json.JsonElement.requiredObject(context: String): JsonObject =
        this as? JsonObject
            ?: throw TutorialDetailFormatException("$context must be an object")

    private fun JsonObject.requiredObject(name: String, context: String): JsonObject =
        this[name]?.requiredObject("$context.$name")
            ?: throw TutorialDetailFormatException("$context has no '$name'")

    private fun JsonObject.optionalObject(name: String, context: String): JsonObject? {
        val value = this[name] ?: throw TutorialDetailFormatException("$context has no '$name'")
        return if (value is JsonNull) null else value.requiredObject("$context.$name")
    }

    private fun JsonObject.requiredArray(name: String, context: String): JsonArray =
        this[name] as? JsonArray
            ?: throw TutorialDetailFormatException("$context has no array '$name'")

    private fun JsonObject.requiredString(name: String, context: String): String {
        val element = this[name]
        val value = if (element == null || element is JsonNull) {
            null
        } else {
            element.jsonPrimitive.content
        }
        if (value.isNullOrBlank()) {
            throw TutorialDetailFormatException("$context has no non-empty '$name'")
        }
        return value
    }

    private fun JsonObject.optionalString(name: String, context: String): String? {
        val value = this[name] ?: throw TutorialDetailFormatException("$context has no '$name'")
        if (value is JsonNull) return null
        val content = value.jsonPrimitive.content
        if (content.isBlank()) {
            throw TutorialDetailFormatException("$context has a blank '$name'")
        }
        return content
    }

    private fun JsonObject.requiredInt(name: String, context: String): Int = try {
        this[name]?.jsonPrimitive?.int
            ?: throw TutorialDetailFormatException("$context has no '$name'")
    } catch (error: IllegalArgumentException) {
        throw TutorialDetailFormatException("$context has an invalid '$name'", error)
    }

    private fun JsonObject.optionalInt(name: String, context: String): Int? {
        val value = this[name] ?: throw TutorialDetailFormatException("$context has no '$name'")
        if (value is JsonNull) return null
        return try {
            value.jsonPrimitive.int
        } catch (error: IllegalArgumentException) {
            throw TutorialDetailFormatException("$context has an invalid '$name'", error)
        }
    }

    private fun JsonObject.requiredDouble(name: String, context: String): Double = try {
        this[name]?.jsonPrimitive?.double
            ?: throw TutorialDetailFormatException("$context has no '$name'")
    } catch (error: IllegalArgumentException) {
        throw TutorialDetailFormatException("$context has an invalid '$name'", error)
    }

    private fun <T> JsonObject.requiredEnum(
        name: String,
        context: String,
        values: List<T>,
        wireName: (T) -> String,
    ): T {
        val raw = requiredString(name, context)
        return values.firstOrNull { wireName(it) == raw }
            ?: throw TutorialDetailFormatException("$context has unknown '$name' value '$raw'")
    }

    private companion object {
        const val SUPPORTED_SCHEMA_VERSION = "1.0"
    }
}
