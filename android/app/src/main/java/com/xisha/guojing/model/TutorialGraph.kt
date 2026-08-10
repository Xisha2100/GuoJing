package com.xisha.guojing.model

data class PublishedTutorialDetail(
    val revisionNumber: Int,
    val publishedAt: String,
    val graph: TutorialGraph,
)

data class TutorialGraph(
    val schemaVersion: String,
    val graphId: String,
    val title: String,
    val recordedApp: AppIdentity,
    val startNodeId: String,
    val nodes: List<TutorialNode>,
    val transitions: List<TutorialTransition>,
) {
    fun node(nodeId: String): TutorialNode? = nodes.firstOrNull { it.nodeId == nodeId }

    fun outgoingTransitions(nodeId: String): List<TutorialTransition> =
        transitions.filter { it.sourceNodeId == nodeId }
}

data class AppIdentity(
    val packageName: String,
    val versionName: String,
    val versionCode: Int,
)

data class TutorialNode(
    val nodeId: String,
    val title: String,
    val anchors: List<ScreenAnchor>,
    val privacyMode: PrivacyMode,
    val verificationStatus: VerificationStatus,
    val lastVerifiedVersionCode: Int?,
)

data class ScreenAnchor(
    val anchorId: String,
    val role: AnchorRole,
    val locator: SemanticLocator,
    val relativeConstraints: List<RelativeConstraint>,
    val boundsFallback: NormalizedBounds?,
)

data class SemanticLocator(
    val resourceId: String?,
    val contentDescription: String?,
    val text: String?,
    val ocrText: String?,
)

data class RelativeConstraint(
    val referenceAnchorId: String,
    val position: RelativePosition,
)

data class NormalizedBounds(
    val left: Double,
    val top: Double,
    val right: Double,
    val bottom: Double,
)

data class TutorialTransition(
    val transitionId: String,
    val sourceNodeId: String,
    val targetNodeId: String,
    val actionKind: ActionKind,
    val instruction: String,
    val riskLevel: RiskLevel,
    val targetAnchorId: String?,
)

enum class AnchorRole(val wireName: String) {
    Required("required"),
    Optional("optional"),
    Forbidden("forbidden"),
}

enum class RelativePosition(val wireName: String) {
    LeftOf("left_of"),
    RightOf("right_of"),
    Above("above"),
    Below("below"),
    Inside("inside"),
    Near("near"),
}

enum class PrivacyMode(val wireName: String) {
    NetworkAllowed("network_allowed"),
    LocalOnly("local_only"),
    CapturePaused("capture_paused"),
}

enum class VerificationStatus(val wireName: String) {
    Verified("verified"),
    Provisional("provisional"),
    Stale("stale"),
}

enum class ActionKind(val wireName: String) {
    Tap("tap"),
    Hold("hold"),
    Scroll("scroll"),
    Input("input"),
    Wait("wait"),
    SystemBack("system_back"),
}

enum class RiskLevel(val wireName: String) {
    Low("low"),
    Sensitive("sensitive"),
    Irreversible("irreversible"),
    Financial("financial"),
}
