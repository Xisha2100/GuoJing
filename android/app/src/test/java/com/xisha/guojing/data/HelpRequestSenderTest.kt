package com.xisha.guojing.data

import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.ScreenshotSanitizationReceipt
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HelpRequestSenderTest {
    @Test
    fun posts_only_the_sanitized_payload_and_parses_the_receipt() = runTest {
        val connection = FakeHttpURLConnection(
            responseBody = RECEIPT,
        )
        var requestedUrl: URL? = null
        val sender = HttpHelpRequestSender(
            client = HttpJsonClient("http://10.0.2.2:8000/") { url ->
                requestedUrl = url
                connection
            },
        )
        val screenshot = InMemoryScreenshot(
            encodedBytes = byteArrayOf(0xff.toByte(), 0xd8.toByte(), 0xff.toByte(), 0xd9.toByte()),
            width = 720,
            height = 1_440,
            sha256 = "a".repeat(64),
        )

        val receipt = sender.send(
            HelpRequestSubmission(
                screenshot = screenshot,
                question = "下一步应该点哪里?",
                receipt = ScreenshotSanitizationReceipt(
                    redactionCount = 1,
                    noSensitiveContentConfirmed = false,
                    sanitizedSha256 = "a".repeat(64),
                ),
                intent = HelpRequestIntent.RECORDED_TUTORIAL,
            ),
        )

        assertEquals("http://10.0.2.2:8000/api/v1/help-requests", requestedUrl.toString())
        assertEquals("POST", connection.requestMethod)
        assertEquals("application/json", connection.getRequestProperty("Content-Type"))
        assertTrue(connection.requestBody.contains("\"intent\":\"recorded_tutorial\""))
        assertTrue(connection.requestBody.contains("\"send_consent\":true"))
        assertTrue(connection.requestBody.contains("\"sanitized_image_base64\":\"/9j/2Q==\""))
        assertEquals("server-request-1", receipt.requestId)
        assertEquals("tutorial_match", receipt.processingRoute)
        assertEquals(HelpRequestProcessingStatus.RECEIVED, receipt.processingStatus)
        assertEquals("/api/v1/help-requests/server-request-1", receipt.statusEndpoint)
        assertTrue(connection.disconnected)
    }

    private class FakeHttpURLConnection(
        responseBody: String,
    ) : HttpURLConnection(URL("http://localhost")) {
        private val body = responseBody.toByteArray(Charsets.UTF_8)
        private val output = ByteArrayOutputStream()
        var disconnected = false
        val requestBody: String get() = output.toString(Charsets.UTF_8.name())

        override fun getResponseCode(): Int = 202

        override fun getInputStream(): InputStream = ByteArrayInputStream(body)

        override fun getOutputStream(): ByteArrayOutputStream = output

        override fun disconnect() {
            disconnected = true
        }

        override fun usingProxy(): Boolean = false

        override fun connect() = Unit
    }

    private companion object {
        val RECEIPT =
            """
            {
              "schema_version": "1.1",
              "request_id": "server-request-1",
              "client_request_id": "client-request-1",
              "intent": "recorded_tutorial",
              "processing_route": "tutorial_match",
              "processing_status": "received",
              "image_disposition": "discarded_after_validation",
              "status_endpoint": "/api/v1/help-requests/server-request-1",
              "received_at": "2026-08-26T00:00:00Z"
            }
            """.trimIndent()
    }
}
