package com.xisha.guojing.data

import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.observation.AnchorEvidence
import com.xisha.guojing.observation.NormalizedScreenBounds
import com.xisha.guojing.observation.ObservationEvidenceSource
import com.xisha.guojing.observation.ObservationRequest
import com.xisha.guojing.observation.ObservationSharingPolicy
import com.xisha.guojing.observation.ObservedApp
import com.xisha.guojing.observation.ScreenObservation
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HelpRequestEvidenceSenderTest {
    @Test
    fun posts_sanitized_anchor_metadata_without_node_text() = runTest {
        val connection = FakeHttpURLConnection(RESPONSE)
        val sender = HttpHelpRequestEvidenceSender(
            client = HttpJsonClient("http://10.0.2.2:8000") { connection },
        )
        val submission = HelpRequestEvidenceSubmission(
            requestId = REQUEST_ID,
            accessToken = "capability-token",
            evidenceId = EVIDENCE_ID,
            packageName = "com.tencent.mm",
            versionName = "8.0.60",
            versionCode = 8_060_000,
            source = EvidenceSource.Accessibility,
            sharingPolicy = EvidenceSharingPolicy.SanitizedNetworkAllowed,
            structureScore = 0.9,
            capturedAt = Instant.parse("2026-08-30T00:00:00Z"),
            expiresAt = Instant.parse("2026-08-30T00:10:00Z"),
            anchors = listOf(
                HelpRequestEvidenceAnchor(
                    "chat_tab",
                    0.95,
                    EvidenceBounds(0.1, 0.8, 0.3, 0.95),
                ),
            ),
        )

        val stored = sender.send(submission)

        assertEquals("POST", connection.requestMethod)
        assertEquals("capability-token", connection.getRequestProperty("X-Help-Request-Token"))
        assertTrue(connection.requestBody.contains("\"evidence_id\":\"$EVIDENCE_ID\""))
        assertTrue(connection.requestBody.contains("\"anchor_id\":\"chat_tab\""))
        assertFalse(connection.requestBody.contains("text"))
        assertFalse(connection.requestBody.contains("ocr"))
        assertEquals(EVIDENCE_ID, stored.evidenceId)
        assertEquals(REQUEST_ID, stored.requestId)
    }

    @Test
    fun refuses_to_convert_a_local_only_observation_to_network_evidence() {
        val observation = observation(ObservationSharingPolicy.LocalOnly)

        val error = runCatching {
            HelpRequestEvidenceSubmission.fromObservation(
                requestId = REQUEST_ID,
                accessToken = "capability-token",
                observation = observation,
            )
        }.exceptionOrNull()

        assertTrue(error is IllegalArgumentException)
    }

    @Test
    fun conversion_preserves_only_structural_anchor_metadata() {
        val evidence = HelpRequestEvidenceSubmission.fromObservation(
            requestId = REQUEST_ID,
            accessToken = "capability-token",
            observation = observation(ObservationSharingPolicy.SanitizedNetworkAllowed),
            evidenceId = EVIDENCE_ID,
            capturedAt = Instant.parse("2026-08-30T00:00:00Z"),
        )

        assertEquals(EVIDENCE_ID, evidence.evidenceId)
        assertEquals(EvidenceSource.Accessibility, evidence.source)
        assertEquals("chat_tab", evidence.anchors.single().anchorId)
        assertEquals(Instant.parse("2026-08-30T00:10:00Z"), evidence.expiresAt)
    }

    private fun observation(sharingPolicy: ObservationSharingPolicy): ScreenObservation = ScreenObservation(
        request = ObservationRequest(
            graphId = "wechat_chat",
            nodeId = "chat_list",
            targetPackageName = "com.tencent.mm",
            anchors = emptyList(),
            privacyMode = PrivacyMode.NetworkAllowed,
        ),
        app = ObservedApp("com.tencent.mm", "8.0.60", 8_060_000),
        anchorEvidence = listOf(
            AnchorEvidence(
                "chat_tab",
                0.95,
                NormalizedScreenBounds(0.1, 0.8, 0.3, 0.95),
            ),
        ),
        structureScore = 0.9,
        sharingPolicy = sharingPolicy,
        evidenceSource = ObservationEvidenceSource.Accessibility,
    )

    private class FakeHttpURLConnection(
        responseBody: String,
    ) : HttpURLConnection(URL("http://localhost")) {
        private val body = responseBody.toByteArray(Charsets.UTF_8)
        private val output = ByteArrayOutputStream()
        val requestBody: String get() = output.toString(Charsets.UTF_8.name())

        override fun getResponseCode(): Int = 202

        override fun getInputStream(): InputStream = ByteArrayInputStream(body)

        override fun getOutputStream(): ByteArrayOutputStream = output

        override fun disconnect() = Unit

        override fun usingProxy(): Boolean = false

        override fun connect() = Unit
    }

    private companion object {
        const val REQUEST_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        const val EVIDENCE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        val RESPONSE =
            """
            {
              "schema_version": "1.0",
              "request_id": "$REQUEST_ID",
              "evidence_id": "$EVIDENCE_ID",
              "package_name": "com.tencent.mm",
              "version_name": "8.0.60",
              "version_code": 8060000,
              "source": "accessibility",
              "sharing_policy": "sanitized_network_allowed",
              "structure_score": 0.9,
              "captured_at": "2026-08-30T00:00:00Z",
              "expires_at": "2026-08-30T00:10:00Z",
              "anchors": [{"anchor_id":"chat_tab", "confidence":0.95}]
            }
            """.trimIndent()
    }
}
