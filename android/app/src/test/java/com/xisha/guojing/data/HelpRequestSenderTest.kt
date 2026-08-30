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
                clientRequestId = CLIENT_REQUEST_ID,
            ),
        )

        assertEquals("http://10.0.2.2:8000/api/v1/help-requests", requestedUrl.toString())
        assertEquals("POST", connection.requestMethod)
        assertEquals("application/json", connection.getRequestProperty("Content-Type"))
        assertTrue(connection.requestBody.contains("\"intent\":\"recorded_tutorial\""))
        assertTrue(connection.requestBody.contains("\"send_consent\":true"))
        assertTrue(connection.requestBody.contains("\"sanitized_image_base64\":\"/9j/2Q==\""))
        assertEquals(REQUEST_ID, receipt.requestId)
        assertEquals(CLIENT_REQUEST_ID, receipt.clientRequestId)
        assertEquals(HelpRequestIntent.RECORDED_TUTORIAL, receipt.intent)
        assertEquals("tutorial_match", receipt.processingRoute)
        assertEquals(HelpRequestProcessingStatus.RECEIVED, receipt.processingStatus)
        assertEquals("/api/v1/help-requests/$REQUEST_ID", receipt.statusEndpoint)
        assertTrue(connection.disconnected)
    }

    @Test
    fun rejects_a_receipt_that_is_not_bound_to_the_submission() = runTest {
        val connection = FakeHttpURLConnection(RECEIPT.replace(CLIENT_REQUEST_ID, OTHER_CLIENT_ID))
        val sender = HttpHelpRequestSender(
            client = HttpJsonClient("http://localhost") { connection },
        )
        val screenshot = InMemoryScreenshot(
            encodedBytes = byteArrayOf(1),
            width = 1,
            height = 1,
            sha256 = "a".repeat(64),
        )

        val error = runCatching {
            sender.send(
                HelpRequestSubmission(
                    screenshot = screenshot,
                    question = "怎么操作？",
                    receipt = ScreenshotSanitizationReceipt(1, false, "a".repeat(64)),
                    intent = HelpRequestIntent.RECORDED_TUTORIAL,
                    clientRequestId = CLIENT_REQUEST_ID,
                ),
            )
        }.exceptionOrNull()

        assertTrue(error is HelpRequestFormatException)
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
              "request_id": "$REQUEST_ID",
              "client_request_id": "$CLIENT_REQUEST_ID",
              "intent": "recorded_tutorial",
              "processing_route": "tutorial_match",
              "processing_status": "received",
              "image_disposition": "discarded_after_validation",
              "status_endpoint": "/api/v1/help-requests/$REQUEST_ID",
              "received_at": "2026-08-26T00:00:00Z"
            }
            """.trimIndent()
        const val REQUEST_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        const val CLIENT_REQUEST_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        const val OTHER_CLIENT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    }
}
