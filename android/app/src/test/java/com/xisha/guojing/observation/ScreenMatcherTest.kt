package com.xisha.guojing.observation

import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.model.VerificationStatus
import com.xisha.guojing.testTutorialDetail
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ScreenMatcherTest {
    private val detail = testTutorialDetail()
    private val graph = detail.graph
    private val node = graph.node(graph.startNodeId)!!

    @Test
    fun strong_required_and_structural_evidence_matches() {
        val result = matchScreen(graph, node, observation(confidence = 1.0, structure = 1.0))

        assertEquals(ScreenMatchStatus.Matched, result.status)
        assertEquals(ScreenMatchReason.StrongMatch, result.reason)
        assertTrue(result.score >= 0.90)
    }

    @Test
    fun missing_required_anchor_is_uncertain() {
        val result = matchScreen(graph, node, observation(confidence = 0.0, structure = 1.0))

        assertEquals(ScreenMatchStatus.Uncertain, result.status)
        assertEquals(ScreenMatchReason.RequiredAnchorMissing, result.reason)
        assertEquals(listOf(node.anchors.single().anchorId), result.missingRequired)
    }

    @Test
    fun forbidden_anchor_forces_mismatch() {
        val forbidden = node.anchors.single().copy(
            anchorId = "password",
            role = AnchorRole.Forbidden,
        )
        val nodeWithForbidden = node.copy(anchors = node.anchors + forbidden)
        val evidence = listOf(
            AnchorEvidence(node.anchors.single().anchorId, 1.0, null),
            AnchorEvidence("password", 0.95, null),
        )

        val result = matchScreen(
            graph,
            nodeWithForbidden,
            observation(confidence = 1.0, structure = 1.0).copy(anchorEvidence = evidence),
        )

        assertEquals(ScreenMatchStatus.Mismatch, result.status)
        assertEquals(ScreenMatchReason.ForbiddenAnchorPresent, result.reason)
    }

    @Test
    fun wrong_package_forces_mismatch() {
        val result = matchScreen(
            graph,
            node,
            observation(confidence = 1.0, structure = 1.0).copy(
                app = ObservedApp("com.example.fake", "1", 1),
            ),
        )

        assertEquals(ScreenMatchStatus.Mismatch, result.status)
        assertEquals(ScreenMatchReason.PackageMismatch, result.reason)
    }

    @Test
    fun version_compatibility_requires_the_same_verified_version() {
        assertEquals(
            VersionCompatibility.SameVerifiedVersion,
            assessVersionCompatibility(node, ObservedApp("com.tencent.mm", "8.0.60", 2600)),
        )
        assertEquals(
            VersionCompatibility.VersionChanged,
            assessVersionCompatibility(node, ObservedApp("com.tencent.mm", "8.0.61", 2601)),
        )
        assertEquals(
            VersionCompatibility.StoredStale,
            assessVersionCompatibility(
                node.copy(verificationStatus = VerificationStatus.Stale),
                ObservedApp("com.tencent.mm", "8.0.60", 2600),
            ),
        )
        assertEquals(
            VersionCompatibility.UnknownCurrentVersion,
            assessVersionCompatibility(node, ObservedApp("com.tencent.mm", "", 0)),
        )
    }

    private fun observation(confidence: Double, structure: Double): ScreenObservation {
        val request = ObservationRequest(
            graphId = graph.graphId,
            nodeId = node.nodeId,
            targetPackageName = graph.recordedApp.packageName,
            anchors = node.anchors,
            privacyMode = node.privacyMode,
        )
        return ScreenObservation(
            request = request,
            app = ObservedApp("com.tencent.mm", "8.0.60", 2600),
            anchorEvidence = listOf(
                AnchorEvidence(node.anchors.single().anchorId, confidence, null),
            ),
            structureScore = structure,
            sharingPolicy = ObservationSharingPolicy.LocalOnly,
        )
    }
}
