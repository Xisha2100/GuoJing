package com.xisha.guojing.observation

import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.testNode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class OcrObservationBuilderTest {
    private val builder = OcrObservationBuilder()

    @Test
    fun on_device_ocr_matches_only_the_explicit_ocr_locator() {
        val request = request(PrivacyMode.LocalOnly)
        val bounds = NormalizedScreenBounds(0.1, 0.2, 0.6, 0.3)

        val observation = builder.build(
            request = request,
            app = observedApp(),
            strategy = OcrStrategy.OnDevice,
            inputKind = OcrInputKind.LocalSession,
            blocks = listOf(
                OcrTextBlock("微信聊天列表", 0.93, bounds),
                OcrTextBlock("微信聊天列表旁边的其他字", 0.99, null),
            ),
        )!!

        assertEquals(0.93, observation.anchorEvidence.single().confidence, 0.001)
        assertEquals(bounds, observation.anchorEvidence.single().normalizedBounds)
        assertEquals(ObservationEvidenceSource.Ocr, observation.evidenceSource)
        assertEquals(OcrStrategy.OnDevice, observation.ocrStrategy)
        assertEquals(OcrInputKind.LocalSession, observation.ocrInputKind)
        assertEquals(ObservationSharingPolicy.LocalOnly, observation.sharingPolicy)
    }

    @Test
    fun network_ocr_requires_a_sanitized_screenshot_and_explicit_network_mode() {
        val request = request(PrivacyMode.LocalOnly)
        assertNull(
            builder.build(
                request,
                observedApp(),
                OcrStrategy.BackendWorker,
                OcrInputKind.SanitizedScreenshot,
                listOf(OcrTextBlock("微信聊天列表", 1.0, null)),
            ),
        )

        val networkRequest = request(PrivacyMode.NetworkAllowed)
        assertNull(
            builder.build(
                networkRequest,
                observedApp(),
                OcrStrategy.VisionModel,
                OcrInputKind.LocalSession,
                listOf(OcrTextBlock("微信聊天列表", 1.0, null)),
            ),
        )
        val observation = builder.build(
            networkRequest,
            observedApp(),
            OcrStrategy.BackendWorker,
            OcrInputKind.SanitizedScreenshot,
            listOf(OcrTextBlock("微信聊天列表", 1.0, null)),
        )!!
        assertEquals(ObservationSharingPolicy.SanitizedNetworkAllowed, observation.sharingPolicy)

        val localObservation = builder.build(
            networkRequest,
            observedApp(),
            OcrStrategy.OnDevice,
            OcrInputKind.LocalSession,
            listOf(OcrTextBlock("微信聊天列表", 1.0, null)),
        )!!
        assertEquals(ObservationSharingPolicy.LocalOnly, localObservation.sharingPolicy)
    }

    @Test
    fun capture_paused_and_package_mismatch_never_produce_ocr_evidence() {
        val paused = builder.build(
            request(PrivacyMode.CapturePaused),
            observedApp(),
            OcrStrategy.OnDevice,
            OcrInputKind.LocalSession,
            emptyList(),
        )
        assertNull(paused)

        val mismatch = builder.build(
            request(PrivacyMode.LocalOnly),
            observedApp(packageName = "com.example.other"),
            OcrStrategy.OnDevice,
            OcrInputKind.LocalSession,
            emptyList(),
        )
        assertNull(mismatch)
    }

    @Test
    fun missing_ocr_locator_does_not_fall_back_to_accessibility_text() {
        val node = testNode("chat_list", "微信聊天列表")
        val request = request(PrivacyMode.LocalOnly).copy(anchors = listOf(node.anchors.single()))
        val observation = builder.build(
            request,
            observedApp(),
            OcrStrategy.OnDevice,
            OcrInputKind.LocalSession,
            listOf(OcrTextBlock("微信聊天列表", 1.0, null)),
        )!!

        assertEquals(0.0, observation.anchorEvidence.single().confidence, 0.001)
    }

    @Test
    fun policy_keeps_on_device_as_the_default_candidate() {
        assertEquals(
            true,
            OcrStrategyPolicy.isAllowed(
                PrivacyMode.LocalOnly,
                OcrStrategy.OnDevice,
                OcrInputKind.LocalSession,
            ),
        )
        assertEquals(
            false,
            OcrStrategyPolicy.isAllowed(
                PrivacyMode.LocalOnly,
                OcrStrategy.VisionModel,
                OcrInputKind.SanitizedScreenshot,
            ),
        )
    }

    private fun request(privacyMode: PrivacyMode): ObservationRequest {
        val node = testNode("chat_list", "微信聊天列表")
        val anchor = node.anchors.single().copy(
            locator = node.anchors.single().locator.copy(
                text = null,
                ocrText = "微信聊天列表",
            ),
        )
        return ObservationRequest(
            graphId = "wechat_open_family_chat",
            nodeId = node.nodeId,
            targetPackageName = "com.tencent.mm",
            anchors = listOf(anchor),
            privacyMode = privacyMode,
        )
    }

    private fun observedApp(packageName: String = "com.tencent.mm") = ObservedApp(
        packageName = packageName,
        versionName = "8.0.60",
        versionCode = 2600,
    )
}
