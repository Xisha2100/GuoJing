package com.xisha.guojing.observation

import com.xisha.guojing.model.NormalizedBounds
import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.ScreenAnchor
import com.xisha.guojing.model.SemanticLocator
import kotlin.math.abs
import kotlin.math.max

/** Converts an ephemeral semantic tree into evidence that contains no raw screen text. */
class SemanticObservationBuilder {
    fun build(
        request: ObservationRequest,
        app: ObservedApp,
        nodes: List<SemanticNodeSnapshot>,
    ): ScreenObservation? {
        if (request.privacyMode == PrivacyMode.CapturePaused) return null
        if (app.packageName != request.targetPackageName) return null

        val evidence = request.anchors.map { anchor ->
            AnchorEvidence(
                anchorId = anchor.anchorId,
                confidence = nodes.maxOfOrNull { node -> confidence(anchor, node) } ?: 0.0,
            )
        }
        val structuralAnchorIds = request.anchors
            .filter { it.role == AnchorRole.Required }
            .ifEmpty { request.anchors.filter { it.role == AnchorRole.Optional } }
            .mapTo(mutableSetOf()) { it.anchorId }
        val structuralEvidence = evidence.filter { it.anchorId in structuralAnchorIds }
        val structureScore = if (structuralEvidence.isEmpty()) {
            0.0
        } else {
            structuralEvidence.count {
                it.confidence >= ANCHOR_PRESENCE_THRESHOLD
            }.toDouble() / structuralEvidence.size
        }
        return ScreenObservation(
            request = request,
            app = app,
            anchorEvidence = evidence,
            structureScore = structureScore,
            sharingPolicy = when (request.privacyMode) {
                PrivacyMode.NetworkAllowed -> ObservationSharingPolicy.SanitizedNetworkAllowed
                PrivacyMode.LocalOnly -> ObservationSharingPolicy.LocalOnly
                PrivacyMode.CapturePaused -> error("capture-paused requests return before collection")
            },
        )
    }

    private fun confidence(anchor: ScreenAnchor, node: SemanticNodeSnapshot): Double = maxOf(
        semanticConfidence(anchor.locator, node),
        boundsConfidence(anchor.boundsFallback, node.normalizedBounds),
    )

    private fun semanticConfidence(
        locator: SemanticLocator,
        node: SemanticNodeSnapshot,
    ): Double {
        var confidence = 0.0
        if (sameIdentifier(locator.resourceId, node.resourceId)) confidence = 1.0
        if (sameText(locator.contentDescription, node.contentDescription)) {
            confidence = max(confidence, 0.95)
        }
        if (sameText(locator.text, node.text)) confidence = max(confidence, 0.90)
        // OCR text is intentionally ignored: AccessibilityService is not an OCR source.
        return confidence
    }

    private fun boundsConfidence(
        expected: NormalizedBounds?,
        actual: NormalizedScreenBounds?,
    ): Double {
        if (expected == null || actual == null) return 0.0
        val distance = listOf(
            abs(expected.left - actual.left),
            abs(expected.top - actual.top),
            abs(expected.right - actual.right),
            abs(expected.bottom - actual.bottom),
        ).average()
        return if (distance <= BOUNDS_TOLERANCE) 0.65 else 0.0
    }

    private fun sameIdentifier(expected: String?, actual: String?): Boolean =
        expected != null && actual != null && expected == actual

    private fun sameText(expected: String?, actual: String?): Boolean =
        expected != null && actual != null && normalize(expected) == normalize(actual)

    private fun normalize(value: String): String = value.trim().lowercase()

    private companion object {
        const val ANCHOR_PRESENCE_THRESHOLD = 0.80
        const val BOUNDS_TOLERANCE = 0.03
    }
}
