package com.xisha.guojing.observation

import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.ScreenAnchor
import kotlin.math.min

/** Providers that may later implement the OCR port. */
enum class OcrStrategy {
    OnDevice,
    BackendWorker,
    VisionModel,
}

/** Whether the recognized pixels were kept only in the session or locally sanitized. */
enum class OcrInputKind {
    LocalSession,
    SanitizedScreenshot,
}

/**
 * Ephemeral provider output. The builder consumes this list and does not return its text.
 * Callers must drop the provider result as soon as the observation has been built.
 */
data class OcrTextBlock(
    val text: String,
    val confidence: Double,
    val normalizedBounds: NormalizedScreenBounds?,
) {
    init {
        require(text.isNotBlank())
        require(confidence in 0.0..1.0)
    }
}

/**
 * Deterministic OCR evidence adapter. It is deliberately independent of any OCR SDK.
 * A future ML Kit, backend worker, or vision adapter should produce [OcrTextBlock]s and
 * then pass them here.
 */
class OcrObservationBuilder {
    fun build(
        request: ObservationRequest,
        app: ObservedApp,
        strategy: OcrStrategy,
        inputKind: OcrInputKind,
        blocks: List<OcrTextBlock>,
    ): ScreenObservation? {
        if (request.privacyMode == PrivacyMode.CapturePaused) return null
        if (app.packageName != request.targetPackageName) return null
        if (!OcrStrategyPolicy.isAllowed(request.privacyMode, strategy, inputKind)) {
            return null
        }

        // Allocate each OCR block at most once.  Without this, a short common
        // word could satisfy several anchors independently and inflate the
        // screen score beyond what the pixels actually support.
        val remainingBlocks = blocks.toMutableList()
        val evidence = request.anchors.map { anchor ->
            val match = bestEvidence(anchor, remainingBlocks)
            if (match != null) {
                remainingBlocks.removeAt(match.blockIndex)
                match.evidence
            } else {
                AnchorEvidence(anchorId = anchor.anchorId, confidence = 0.0, normalizedBounds = null)
            }
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
            sharingPolicy = if (strategy == OcrStrategy.OnDevice) {
                ObservationSharingPolicy.LocalOnly
            } else {
                ObservationSharingPolicy.SanitizedNetworkAllowed
            },
            evidenceSource = ObservationEvidenceSource.Ocr,
            ocrStrategy = strategy,
            ocrInputKind = inputKind,
        )
    }

    private fun bestEvidence(
        anchor: ScreenAnchor,
        blocks: List<OcrTextBlock>,
    ): BlockMatch? {
        val expected = anchor.locator.ocrText?.let(::normalize)
        if (expected == null || expected.isBlank()) return null
        val best = blocks.mapIndexed { index, block ->
            index to matchConfidence(expected, normalize(block.text), block.confidence)
        }.maxByOrNull { (_, confidence) -> confidence }
            ?.takeIf { (_, confidence) -> confidence > 0.0 }
            ?: return null
        val (blockIndex, confidence) = best
        val block = blocks[blockIndex]
        return BlockMatch(
            blockIndex = blockIndex,
            evidence = AnchorEvidence(
            anchorId = anchor.anchorId,
            confidence = confidence,
            normalizedBounds = block.normalizedBounds.takeIf {
                confidence >= ANCHOR_PRESENCE_THRESHOLD
            },
            ),
        )
    }

    private fun matchConfidence(expected: String, actual: String, providerConfidence: Double): Double {
        if (actual.isBlank()) return 0.0
        val textMatch = when {
            expected == actual -> 1.0
            expected.length >= MINIMUM_SUBSTRING_LENGTH &&
                actual.length >= MINIMUM_SUBSTRING_LENGTH &&
                min(expected.length, actual.length).toDouble() /
                    maxOf(expected.length, actual.length) >= MINIMUM_COVERAGE &&
                (actual.contains(expected) || expected.contains(actual)) -> SUBSTRING_MATCH
            else -> 0.0
        }
        return min(textMatch * providerConfidence, 1.0)
    }

    private fun normalize(value: String): String = value
        .trim()
        .lowercase()
        .filter { it.isLetterOrDigit() }

    private data class BlockMatch(
        val blockIndex: Int,
        val evidence: AnchorEvidence,
    )

    private companion object {
        const val ANCHOR_PRESENCE_THRESHOLD = 0.80
        const val MINIMUM_SUBSTRING_LENGTH = 2
        const val MINIMUM_COVERAGE = 0.80
        const val SUBSTRING_MATCH = 0.75
    }
}

object OcrStrategyPolicy {
    /**
     * Network OCR is legal only for an explicitly allowed, locally sanitized screenshot.
     * On-device OCR never needs a network boundary and is therefore the first strategy for
     * both local-only and network-allowed sessions.
     */
    fun isAllowed(
        privacyMode: PrivacyMode,
        strategy: OcrStrategy,
        inputKind: OcrInputKind,
    ): Boolean {
        if (privacyMode == PrivacyMode.CapturePaused) return false
        return when (strategy) {
            OcrStrategy.OnDevice -> inputKind == OcrInputKind.LocalSession ||
                inputKind == OcrInputKind.SanitizedScreenshot
            OcrStrategy.BackendWorker,
            OcrStrategy.VisionModel,
            -> privacyMode == PrivacyMode.NetworkAllowed &&
                inputKind == OcrInputKind.SanitizedScreenshot
        }
    }
}
