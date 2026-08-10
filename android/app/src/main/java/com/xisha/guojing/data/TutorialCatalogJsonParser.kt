package com.xisha.guojing.data

import com.xisha.guojing.model.TutorialSummary
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive

class TutorialCatalogFormatException(
    message: String,
    cause: Throwable? = null,
) : IllegalArgumentException(message, cause)

internal class TutorialCatalogJsonParser(
    private val json: Json = Json,
) {
    fun parse(payload: String): List<TutorialSummary> = try {
        val root = json.parseToJsonElement(payload)
        val items = root as? JsonArray
            ?: throw TutorialCatalogFormatException("Tutorial catalog must be a JSON array")
        items.mapIndexed { index, element ->
            val item = element as? JsonObject
                ?: throw TutorialCatalogFormatException("Tutorial at index $index must be an object")
            TutorialSummary(
                graphId = item.requiredString("graph_id", index),
                title = item.requiredString("title", index),
                packageName = item.requiredString("package_name", index),
                recordedVersionName = item.requiredString("recorded_version_name", index),
                recordedVersionCode = item.requiredInt("recorded_version_code", index),
                revisionNumber = item.requiredInt("revision_number", index),
                publishedAt = item.requiredString("published_at", index),
            )
        }
    } catch (error: TutorialCatalogFormatException) {
        throw error
    } catch (error: IllegalArgumentException) {
        throw TutorialCatalogFormatException("Tutorial catalog contains invalid JSON", error)
    }

    private fun JsonObject.requiredString(name: String, index: Int): String {
        val element = this[name]
        val value = if (element == null || element is JsonNull) {
            null
        } else {
            element.jsonPrimitive.content
        }
        if (value.isNullOrBlank()) {
            throw TutorialCatalogFormatException(
                "Tutorial at index $index has no non-empty '$name'",
            )
        }
        return value
    }

    private fun JsonObject.requiredInt(name: String, index: Int): Int = try {
        this[name]?.jsonPrimitive?.int
            ?: throw TutorialCatalogFormatException("Tutorial at index $index has no '$name'")
    } catch (error: IllegalArgumentException) {
        throw TutorialCatalogFormatException(
            "Tutorial at index $index has an invalid '$name'",
            error,
        )
    }
}
