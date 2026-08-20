package com.xisha.guojing.observation

import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.AnchorRole
import com.xisha.guojing.testNode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SemanticObservationBuilderTest {
    private val builder = SemanticObservationBuilder()

    @Test
    fun local_only_tree_becomes_sanitized_anchor_evidence() {
        val request = request(PrivacyMode.LocalOnly)

        val observation = builder.build(
            request = request,
            app = observedApp(),
            nodes = listOf(
                SemanticNodeSnapshot(
                    resourceId = null,
                    contentDescription = null,
                    text = "微信聊天列表",
                    normalizedBounds = null,
                ),
            ),
        )!!

        assertEquals(0.90, observation.anchorEvidence.single().confidence, 0.001)
        assertEquals(ObservationSharingPolicy.LocalOnly, observation.sharingPolicy)
        assertEquals(1.0, observation.structureScore, 0.001)
    }

    @Test
    fun capture_paused_refuses_to_build_any_observation() {
        val observation = builder.build(
            request = request(PrivacyMode.CapturePaused),
            app = observedApp(),
            nodes = listOf(
                SemanticNodeSnapshot(null, null, "验证码 123456", null),
            ),
        )

        assertNull(observation)
    }

    @Test
    fun a_different_package_is_ignored() {
        val observation = builder.build(
            request = request(PrivacyMode.NetworkAllowed),
            app = observedApp(packageName = "com.example.fake"),
            nodes = emptyList(),
        )

        assertNull(observation)
    }

    @Test
    fun resource_id_is_stronger_than_text_fallback() {
        val node = testNode("chat_list")
        val anchor = node.anchors.single().copy(
            locator = node.anchors.single().locator.copy(resourceId = "com.tencent.mm:id/list"),
        )
        val request = request(PrivacyMode.NetworkAllowed).copy(anchors = listOf(anchor))

        val observation = builder.build(
            request = request,
            app = observedApp(),
            nodes = listOf(
                SemanticNodeSnapshot(
                    resourceId = "com.tencent.mm:id/list",
                    contentDescription = null,
                    text = "changed label",
                    normalizedBounds = null,
                ),
            ),
        )!!

        assertEquals(1.0, observation.anchorEvidence.single().confidence, 0.001)
        assertEquals(
            ObservationSharingPolicy.SanitizedNetworkAllowed,
            observation.sharingPolicy,
        )
    }

    @Test
    fun absent_forbidden_and_optional_anchors_do_not_reduce_structure_score() {
        val required = testNode("chat_list", "微信聊天列表").anchors.single()
        val forbidden = required.copy(
            anchorId = "password",
            role = AnchorRole.Forbidden,
            locator = required.locator.copy(text = "支付密码"),
        )
        val optional = required.copy(
            anchorId = "search",
            role = AnchorRole.Optional,
            locator = required.locator.copy(text = "搜索"),
        )
        val request = request(PrivacyMode.LocalOnly).copy(
            anchors = listOf(required, optional, forbidden),
        )

        val observation = builder.build(
            request = request,
            app = observedApp(),
            nodes = listOf(SemanticNodeSnapshot(null, null, "微信聊天列表", null)),
        )!!

        assertEquals(1.0, observation.structureScore, 0.001)
        assertEquals(0.0, observation.anchorEvidence[1].confidence, 0.001)
        assertEquals(0.0, observation.anchorEvidence[2].confidence, 0.001)
    }

    private fun request(privacyMode: PrivacyMode): ObservationRequest {
        val node = testNode("chat_list", "微信聊天列表")
        return ObservationRequest(
            graphId = "wechat_open_family_chat",
            nodeId = node.nodeId,
            targetPackageName = "com.tencent.mm",
            anchors = node.anchors,
            privacyMode = privacyMode,
        )
    }

    private fun observedApp(packageName: String = "com.tencent.mm") = ObservedApp(
        packageName = packageName,
        versionName = "8.0.60",
        versionCode = 2600,
    )
}
