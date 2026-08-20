package com.xisha.guojing.observation

import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.ScreenAnchor

data class ObservationRequest(
    val graphId: String,
    val nodeId: String,
    val targetPackageName: String,
    val anchors: List<ScreenAnchor>,
    val privacyMode: PrivacyMode,
)

data class ObservedApp(
    val packageName: String,
    val versionName: String,
    val versionCode: Long,
)

data class AnchorEvidence(
    val anchorId: String,
    val confidence: Double,
)

data class ScreenObservation(
    val request: ObservationRequest,
    val app: ObservedApp,
    val anchorEvidence: List<AnchorEvidence>,
    val structureScore: Double,
    val sharingPolicy: ObservationSharingPolicy,
)

enum class ObservationSharingPolicy {
    SanitizedNetworkAllowed,
    LocalOnly,
}

sealed interface ObservationState {
    data object Idle : ObservationState

    data class Waiting(
        val request: ObservationRequest,
    ) : ObservationState

    data class CapturePaused(
        val request: ObservationRequest,
    ) : ObservationState

    data class Available(
        val observation: ScreenObservation,
    ) : ObservationState
}

data class SemanticNodeSnapshot(
    val resourceId: String?,
    val contentDescription: String?,
    val text: String?,
    val normalizedBounds: NormalizedScreenBounds?,
)

data class NormalizedScreenBounds(
    val left: Double,
    val top: Double,
    val right: Double,
    val bottom: Double,
)
