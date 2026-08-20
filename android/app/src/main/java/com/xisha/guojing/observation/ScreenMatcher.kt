package com.xisha.guojing.observation

import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.model.TutorialNode

enum class ScreenMatchStatus {
    Matched,
    Uncertain,
    Mismatch,
}

enum class ScreenMatchReason {
    StrongMatch,
    PackageMismatch,
    ForbiddenAnchorPresent,
    RequiredAnchorMissing,
    ScoreBelowThreshold,
}

data class ScreenMatchResult(
    val status: ScreenMatchStatus,
    val score: Double,
    val matchedRequired: List<String>,
    val missingRequired: List<String>,
    val matchedOptional: List<String>,
    val matchedForbidden: List<String>,
    val reason: ScreenMatchReason,
)

/** Kotlin counterpart of the backend's deterministic screen-matching policy. */
fun matchScreen(
    graph: TutorialGraph,
    node: TutorialNode,
    observation: ScreenObservation,
): ScreenMatchResult {
    if (observation.app.packageName != graph.recordedApp.packageName) {
        return mismatch(ScreenMatchReason.PackageMismatch)
    }

    val confidenceByAnchor = observation.anchorEvidence
        .groupBy(AnchorEvidence::anchorId)
        .mapValues { (_, evidence) -> evidence.maxOf(AnchorEvidence::confidence) }
    val required = node.anchors.filter { it.role == AnchorRole.Required }
    val optional = node.anchors.filter { it.role == AnchorRole.Optional }
    val forbidden = node.anchors.filter { it.role == AnchorRole.Forbidden }
    val matchedRequired = required.presentIds(confidenceByAnchor)
    val missingRequired = required.map { it.anchorId } - matchedRequired.toSet()
    val matchedOptional = optional.presentIds(confidenceByAnchor)
    val matchedForbidden = forbidden.presentIds(confidenceByAnchor)

    if (matchedForbidden.isNotEmpty()) {
        return ScreenMatchResult(
            status = ScreenMatchStatus.Mismatch,
            score = 0.0,
            matchedRequired = matchedRequired,
            missingRequired = missingRequired,
            matchedOptional = matchedOptional,
            matchedForbidden = matchedForbidden,
            reason = ScreenMatchReason.ForbiddenAnchorPresent,
        )
    }

    val score = REQUIRED_WEIGHT * required.averageConfidence(confidenceByAnchor) +
        OPTIONAL_WEIGHT * optional.averageConfidence(confidenceByAnchor) +
        STRUCTURE_WEIGHT * observation.structureScore
    val status = when {
        missingRequired.isNotEmpty() -> ScreenMatchStatus.Uncertain
        score < MATCHED_SCORE_THRESHOLD -> ScreenMatchStatus.Uncertain
        else -> ScreenMatchStatus.Matched
    }
    val reason = when {
        missingRequired.isNotEmpty() -> ScreenMatchReason.RequiredAnchorMissing
        score < MATCHED_SCORE_THRESHOLD -> ScreenMatchReason.ScoreBelowThreshold
        else -> ScreenMatchReason.StrongMatch
    }
    return ScreenMatchResult(
        status = status,
        score = score,
        matchedRequired = matchedRequired,
        missingRequired = missingRequired,
        matchedOptional = matchedOptional,
        matchedForbidden = emptyList(),
        reason = reason,
    )
}

private fun List<com.xisha.guojing.model.ScreenAnchor>.presentIds(
    confidenceByAnchor: Map<String, Double>,
): List<String> = filter {
    confidenceByAnchor.getOrDefault(it.anchorId, 0.0) >= ANCHOR_PRESENCE_THRESHOLD
}.map { it.anchorId }

private fun List<com.xisha.guojing.model.ScreenAnchor>.averageConfidence(
    confidenceByAnchor: Map<String, Double>,
): Double = if (isEmpty()) {
    0.0
} else {
    sumOf { confidenceByAnchor.getOrDefault(it.anchorId, 0.0) } / size
}

private fun mismatch(reason: ScreenMatchReason) = ScreenMatchResult(
    status = ScreenMatchStatus.Mismatch,
    score = 0.0,
    matchedRequired = emptyList(),
    missingRequired = emptyList(),
    matchedOptional = emptyList(),
    matchedForbidden = emptyList(),
    reason = reason,
)

private const val ANCHOR_PRESENCE_THRESHOLD = 0.80
private const val MATCHED_SCORE_THRESHOLD = 0.90
private const val REQUIRED_WEIGHT = 0.75
private const val OPTIONAL_WEIGHT = 0.10
private const val STRUCTURE_WEIGHT = 0.15
