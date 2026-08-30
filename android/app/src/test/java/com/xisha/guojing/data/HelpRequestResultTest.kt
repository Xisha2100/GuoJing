package com.xisha.guojing.data

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class HelpRequestResultTest {
    @Test
    fun status_reader_parses_manual_guidance_and_uses_the_request_id_path() = runTest {
        val connection = FakeHttpURLConnection(GUIDANCE_RESULT)
        var requestedUrl: URL? = null
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://10.0.2.2:8000") { url ->
                requestedUrl = url
                connection
            },
        )

        val result = reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")

        assertEquals(
            "http://10.0.2.2:8000/api/v1/help-requests/11111111-1111-4111-8111-111111111111",
            requestedUrl.toString(),
        )
        assertEquals(HelpRequestProcessingStatus.GUIDANCE_READY, result.processingStatus)
        assertEquals("基础指引", result.guidance?.title)
        assertEquals("请你亲自确认页面标题。", result.guidance?.steps?.single()?.instruction)
        assertTrue(connection.disconnected)
    }

    @Test
    fun status_reader_parses_a_persisted_tutorial_match_checkpoint() = runTest {
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://localhost") {
                FakeHttpURLConnection(TUTORIAL_MATCHED_RESULT)
            },
        )

        val result = reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")

        assertEquals(HelpRequestWorkflowStage.TUTORIAL_MATCHED, result.workflowStage)
        assertEquals("matched", result.tutorialMatch?.status)
        assertEquals("wechat_open_family_chat", result.tutorialMatch?.graphId)
        assertEquals("chat_list", result.tutorialMatch?.nodeId)
        assertEquals(1, result.tutorialMatch?.revisionNumber)
        assertEquals(listOf("open_family_chat"), result.tutorialPlan?.allowedTransitionIds)
    }

    @Test
    fun status_reader_rejects_an_unknown_workflow_stage() = runTest {
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://localhost") {
                FakeHttpURLConnection(TUTORIAL_MATCHED_RESULT.replace("tutorial_matched", "future"))
            },
        )

        val error = runCatching {
            reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")
        }.exceptionOrNull()

        assertTrue(error is HelpRequestFormatException)
    }

    @Test
    fun status_reader_rejects_unknown_processing_status() = runTest {
        val connection = FakeHttpURLConnection(GUIDANCE_RESULT.replace("guidance_ready", "future"))
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://localhost") { connection },
        )

        val error = runCatching {
            reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")
        }.exceptionOrNull()

        assertTrue(error is HelpRequestFormatException)
    }

    @Test
    fun status_reader_rejects_a_response_for_another_request() = runTest {
        val connection = FakeHttpURLConnection(
            GUIDANCE_RESULT.replace(
                "11111111-1111-4111-8111-111111111111",
                "33333333-3333-4333-8333-333333333333",
            ),
        )
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://localhost") { connection },
        )

        val error = runCatching {
            reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")
        }.exceptionOrNull()

        assertTrue(error is HelpRequestFormatException)
    }

    @Test
    fun status_reader_rejects_guidance_that_can_be_interpreted_as_an_automation_command() = runTest {
        val connection = FakeHttpURLConnection(
            GUIDANCE_RESULT.replace("\"requires_manual_action\": true", "\"requires_manual_action\": false"),
        )
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://localhost") { connection },
        )

        val error = runCatching {
            reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")
        }.exceptionOrNull()

        assertTrue(error is HelpRequestFormatException)
    }

    @Test
    fun status_reader_rejects_dangerous_guidance_language() = runTest {
        val connection = FakeHttpURLConnection(
            GUIDANCE_RESULT.replace("请你亲自确认页面标题。", "请点击支付并输入密码。"),
        )
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://localhost") { connection },
        )

        val error = runCatching {
            reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")
        }.exceptionOrNull()

        assertTrue(error is HelpRequestFormatException)
    }

    @Test
    fun status_reader_rejects_dangerous_guidance_title_and_step_title() = runTest {
        val dangerousTitle = GUIDANCE_RESULT.replace(
            "\"title\": \"基础指引\"",
            "\"title\": \"请 点 击 支 付\"",
        )
        val dangerousStepTitle = GUIDANCE_RESULT.replace(
            "\"title\": \"先看标题\"",
            "\"title\": \"确认购买\"",
        )
        val reader = HttpHelpRequestStatusReader(
            client = HttpJsonClient("http://localhost") { _ ->
                FakeHttpURLConnection(dangerousTitle)
            },
        )

        val titleError = runCatching {
            reader.fetch("11111111-1111-4111-8111-111111111111", "capability-token")
        }.exceptionOrNull()
        val stepError = runCatching {
            HttpHelpRequestStatusReader(
                client = HttpJsonClient("http://localhost") { _ ->
                    FakeHttpURLConnection(dangerousStepTitle)
                },
            ).fetch("11111111-1111-4111-8111-111111111111", "capability-token")
        }.exceptionOrNull()

        assertTrue(titleError is HelpRequestFormatException)
        assertTrue(stepError is HelpRequestFormatException)
    }

    @Test
    fun status_reader_rejects_non_uuid_path_input() = runTest {
        val reader = HttpHelpRequestStatusReader("http://localhost")

        val error = runCatching { reader.fetch("../../admin", "capability-token") }.exceptionOrNull()

        assertTrue(error is HelpRequestFormatException)
    }

    private class FakeHttpURLConnection(
        responseBody: String,
    ) : HttpURLConnection(URL("http://localhost")) {
        private val body = responseBody.toByteArray(Charsets.UTF_8)
        private val output = ByteArrayOutputStream()
        var disconnected = false

        override fun getResponseCode(): Int = 200

        override fun getInputStream(): InputStream = ByteArrayInputStream(body)

        override fun getOutputStream(): ByteArrayOutputStream = output

        override fun disconnect() {
            disconnected = true
        }

        override fun usingProxy(): Boolean = false

        override fun connect() = Unit
    }

    private companion object {
        val GUIDANCE_RESULT =
            """
            {
              "schema_version": "1.2",
              "request_id": "11111111-1111-4111-8111-111111111111",
              "client_request_id": "22222222-2222-2222-2222-222222222222",
              "intent": "general_guidance",
              "processing_route": "general_guidance",
              "processing_status": "guidance_ready",
              "received_at": "2026-08-29T00:00:00Z",
              "updated_at": "2026-08-29T00:01:00Z",
              "guidance": {
                "title": "基础指引",
                "steps": [{
                  "step_id": "read-title",
                  "title": "先看标题",
                  "instruction": "请你亲自确认页面标题。",
                  "requires_manual_action": true
                }]
              },
              "human_review_reason": null,
              "workflow_stage": "completed",
              "tutorial_match": null
            }
            """.trimIndent()

        val TUTORIAL_MATCHED_RESULT =
            """
            {
              "schema_version": "1.2",
              "request_id": "11111111-1111-4111-8111-111111111111",
              "client_request_id": "22222222-2222-2222-2222-222222222222",
              "intent": "recorded_tutorial",
              "processing_route": "tutorial_match",
              "processing_status": "needs_human_review",
              "received_at": "2026-08-29T00:00:00Z",
              "updated_at": "2026-08-29T00:01:00Z",
              "guidance": null,
              "human_review_reason": "教程页面已匹配,请人工确认版本和步骤后发布安全说明。",
              "workflow_stage": "tutorial_matched",
              "tutorial_match": {
                "status": "matched",
                "reason": "strong_match",
                "graph_id": "wechat_open_family_chat",
                "node_id": "chat_list",
                "revision_number": 1
              },
              "tutorial_plan": {
                "graph_id": "wechat_open_family_chat",
                "node_id": "chat_list",
                "revision_number": 1,
                "compatibility_status": "verified",
                "allowed_transition_ids": ["open_family_chat"]
              }
            }
            """.trimIndent()
    }
}
