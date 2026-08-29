package com.xisha.guojing.ui.help

import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.ScreenshotPrivacyProcessor
import com.xisha.guojing.data.HelpRequestIntent
import com.xisha.guojing.data.HelpRequestProcessingStatus
import com.xisha.guojing.data.HelpRequestReceipt
import com.xisha.guojing.data.HelpRequestResult
import com.xisha.guojing.data.HelpRequestSender
import com.xisha.guojing.data.HelpRequestSubmission
import com.xisha.guojing.data.HelpRequestStatusReader
import com.xisha.guojing.ui.catalog.MainDispatcherRule
import com.xisha.guojing.observation.NormalizedScreenBounds
import com.xisha.guojing.observation.OcrTextBlock
import com.xisha.guojing.observation.ScreenshotOcrProvider
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ScreenshotHelpViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun picker_uri_is_consumed_without_becoming_ui_state() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(processor)

            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()

            assertEquals("content://picker/42", processor.lastImportedUri)
            assertTrue(viewModel.uiState.value is ScreenshotHelpUiState.Editing)
            assertFalse(viewModel.uiState.value.toString().contains("content://picker/42"))
        }

    @Test
    fun sanitization_requires_a_question_and_explicit_privacy_decision() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(processor)
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()

            viewModel.updateQuestion("下一步应该点哪里？")
            viewModel.sanitize()
            advanceUntilIdle()

            assertEquals(0, processor.sanitizeCalls)
            val editing = viewModel.uiState.value as ScreenshotHelpUiState.Editing
            assertFalse(editing.canSanitize)
        }

    @Test
    fun successful_redaction_replaces_and_erases_the_raw_copy() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(processor)
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            val raw = (viewModel.uiState.value as ScreenshotHelpUiState.Editing).screenshot
            val redaction = requireNotNull(
                NormalizedRedaction.fromDrag(0.1f, 0.2f, 0.6f, 0.4f),
            )

            viewModel.updateQuestion("这个页面怎么返回？")
            viewModel.addRedaction(redaction)
            viewModel.sanitize()
            advanceUntilIdle()

            val ready = viewModel.uiState.value as ScreenshotHelpUiState.Ready
            assertEquals(listOf(redaction), processor.lastRedactions)
            assertEquals(1, ready.receipt.redactionCount)
            assertEquals("这个页面怎么返回？", ready.question)
            assertTrue(raw.encodedBytes.all { it == 0.toByte() })
            assertFalse(ready.screenshot.encodedBytes.all { it == 0.toByte() })
        }

    @Test
    fun no_sensitive_content_confirmation_allows_a_zero_mask_copy() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(processor)
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()

            viewModel.updateQuestion("这个按钮是什么？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()

            val ready = viewModel.uiState.value as ScreenshotHelpUiState.Ready
            assertTrue(ready.receipt.noSensitiveContentConfirmed)
            assertEquals(0, ready.receipt.redactionCount)
        }

    @Test
    fun sanitization_failure_keeps_the_raw_copy_for_a_safe_retry() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor(failSanitization = true)
            val viewModel = ScreenshotHelpViewModel(processor)
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            val raw = (viewModel.uiState.value as ScreenshotHelpUiState.Editing).screenshot

            viewModel.updateQuestion("怎么操作？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()

            val editing = viewModel.uiState.value as ScreenshotHelpUiState.Editing
            assertEquals(ScreenshotHelpError.SanitizationFailed, editing.error)
            assertTrue(raw.encodedBytes.any { it != 0.toByte() })
        }

    @Test
    fun every_ocr_privacy_suggestion_requires_a_decision_before_sanitizing() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val ocrProvider = FakeScreenshotOcrProvider(
                blocks = listOf(
                    OcrTextBlock(
                        text = "电话 13800138000",
                        confidence = 0.95,
                        normalizedBounds = NormalizedScreenBounds(0.1, 0.2, 0.8, 0.3),
                    ),
                ),
            )
            val viewModel = ScreenshotHelpViewModel(
                processor = processor,
                ocrProvider = ocrProvider,
            )
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()

            viewModel.updateQuestion("下一步应该点哪里？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()

            assertEquals(0, processor.sanitizeCalls)
            val pending = viewModel.uiState.value as ScreenshotHelpUiState.Editing
            assertEquals(1, pending.privacySuggestions.size)
            assertFalse(pending.canSanitize)

            viewModel.acceptPrivacySuggestion(pending.privacySuggestions.single().id)
            val accepted = viewModel.uiState.value as ScreenshotHelpUiState.Editing
            assertEquals(1, accepted.redactions.size)
            assertTrue(accepted.canSanitize)

            viewModel.sanitize()
            advanceUntilIdle()
            val ready = viewModel.uiState.value as ScreenshotHelpUiState.Ready
            assertEquals(1, processor.sanitizeCalls)
            assertEquals(1, ready.receipt.redactionCount)
        }

    @Test
    fun rejected_ocr_suggestion_can_be_replaced_by_explicit_no_sensitive_confirmation() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(
                processor = processor,
                ocrProvider = FakeScreenshotOcrProvider(
                    blocks = listOf(
                        OcrTextBlock(
                            text = "订单号",
                            confidence = 0.9,
                            normalizedBounds = NormalizedScreenBounds(0.1, 0.2, 0.8, 0.3),
                        ),
                    ),
                ),
            )
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            val editing = viewModel.uiState.value as ScreenshotHelpUiState.Editing
            viewModel.rejectPrivacySuggestion(editing.privacySuggestions.single().id)
            viewModel.updateQuestion("这个页面怎么操作？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()

            val ready = viewModel.uiState.value as ScreenshotHelpUiState.Ready
            assertEquals(1, processor.sanitizeCalls)
            assertEquals(0, ready.receipt.redactionCount)
            assertTrue(ready.receipt.noSensitiveContentConfirmed)
        }

    @Test
    fun ocr_failure_does_not_block_manual_privacy_review() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(
                processor = processor,
                ocrProvider = FakeScreenshotOcrProvider(fail = true),
            )
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            val editing = viewModel.uiState.value as ScreenshotHelpUiState.Editing
            assertEquals(ScreenshotHelpError.OcrFailed, editing.error)

            viewModel.updateQuestion("怎么操作？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()

            assertTrue(viewModel.uiState.value is ScreenshotHelpUiState.Ready)
        }

    @Test
    fun discard_best_effort_erases_the_session_image() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(processor)
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            val raw = (viewModel.uiState.value as ScreenshotHelpUiState.Editing).screenshot

            viewModel.discard()

            assertTrue(raw.encodedBytes.all { it == 0.toByte() })
            assertEquals(
                ScreenshotHelpUiState.AwaitingSelection(),
                viewModel.uiState.value,
            )
        }

    @Test
    fun sending_requires_consent_and_erases_the_sanitized_copy_after_success() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val sender = FakeHelpRequestSender()
            val viewModel = ScreenshotHelpViewModel(processor, sender)
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            viewModel.updateQuestion("哪个按钮可以继续？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()
            val ready = viewModel.uiState.value as ScreenshotHelpUiState.Ready
            val sanitized = ready.screenshot

            viewModel.send()
            advanceUntilIdle()
            assertEquals(0, sender.sendCalls)
            assertTrue(viewModel.uiState.value is ScreenshotHelpUiState.Ready)

            viewModel.setSendConsent(true)
            viewModel.selectIntent(HelpRequestIntent.GENERAL_GUIDANCE)
            viewModel.send()
            advanceUntilIdle()

            val submitted = viewModel.uiState.value as ScreenshotHelpUiState.Submitted
            assertEquals("server-request-1", submitted.serverReceipt.requestId)
            assertEquals(1, sender.sendCalls)
            assertEquals(HelpRequestIntent.GENERAL_GUIDANCE, sender.lastSubmission?.intent)
            assertTrue(sanitized.encodedBytes.all { it == 0.toByte() })
        }

    @Test
    fun failed_send_keeps_the_sanitized_copy_for_retry() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(
                processor,
                FakeHelpRequestSender(fail = true),
            )
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            viewModel.updateQuestion("怎么操作？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()
            val ready = viewModel.uiState.value as ScreenshotHelpUiState.Ready
            viewModel.setSendConsent(true)
            viewModel.send()
            advanceUntilIdle()

            val failed = viewModel.uiState.value as ScreenshotHelpUiState.Ready
            assertEquals(ScreenshotHelpError.SendFailed, failed.error)
            assertTrue(ready.screenshot.encodedBytes.any { it != 0.toByte() })
        }

    @Test
    fun submitted_request_can_refresh_processing_status_without_an_image() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val statusReader = FakeHelpRequestStatusReader(
                result = HelpRequestResult(
                    requestId = "server-request-1",
                    clientRequestId = "client-request-1",
                    intent = HelpRequestIntent.GENERAL_GUIDANCE,
                    processingRoute = "general_guidance",
                    processingStatus = HelpRequestProcessingStatus.GUIDANCE_READY,
                    receivedAt = "2026-08-29T00:00:00Z",
                    updatedAt = "2026-08-29T00:01:00Z",
                    guidance = com.xisha.guojing.data.HelpRequestGuidance(
                        title = "基础指引",
                        steps = listOf(
                            com.xisha.guojing.data.HelpRequestGuidanceStep(
                                stepId = "one",
                                title = "先看标题",
                                instruction = "请你自己确认页面顶部标题。",
                            ),
                        ),
                    ),
                ),
            )
            val viewModel = ScreenshotHelpViewModel(
                processor = processor,
                sender = FakeHelpRequestSender(),
                statusReader = statusReader,
            )
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            viewModel.updateQuestion("怎么操作？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()
            viewModel.setSendConsent(true)
            viewModel.send()
            advanceUntilIdle()

            viewModel.refreshStatus()
            advanceUntilIdle()

            val submitted = viewModel.uiState.value as ScreenshotHelpUiState.Submitted
            assertEquals(HelpRequestProcessingStatus.GUIDANCE_READY, submitted.processingStatus)
            assertEquals(1, submitted.guidance?.steps?.size)
            assertEquals("server-request-1", statusReader.lastRequestId)
        }

    @Test
    fun failed_status_refresh_keeps_submitted_state_and_exposes_retry_error() =
        runTest(mainDispatcherRule.dispatcher) {
            val processor = FakeScreenshotPrivacyProcessor()
            val viewModel = ScreenshotHelpViewModel(
                processor = processor,
                sender = FakeHelpRequestSender(),
                statusReader = FakeHelpRequestStatusReader(fail = true),
            )
            viewModel.importScreenshot("content://picker/42")
            advanceUntilIdle()
            viewModel.updateQuestion("怎么操作？")
            viewModel.setNoSensitiveContentConfirmed(true)
            viewModel.sanitize()
            advanceUntilIdle()
            viewModel.setSendConsent(true)
            viewModel.send()
            advanceUntilIdle()

            viewModel.refreshStatus()
            advanceUntilIdle()

            val submitted = viewModel.uiState.value as ScreenshotHelpUiState.Submitted
            assertEquals(ScreenshotHelpError.StatusFetchFailed, submitted.statusError)
            assertFalse(submitted.isRefreshingStatus)
        }

    private class FakeScreenshotPrivacyProcessor(
        private val failSanitization: Boolean = false,
    ) : ScreenshotPrivacyProcessor {
        var lastImportedUri: String? = null
        var lastRedactions: List<NormalizedRedaction> = emptyList()
        var sanitizeCalls = 0

        override suspend fun importFromPicker(uriString: String): InMemoryScreenshot {
            lastImportedUri = uriString
            return image(byteArrayOf(1, 2, 3, 4), digestCharacter = 'a')
        }

        override suspend fun sanitize(
            source: InMemoryScreenshot,
            redactions: List<NormalizedRedaction>,
        ): InMemoryScreenshot {
            sanitizeCalls += 1
            lastRedactions = redactions
            if (failSanitization) error("local encoder failed")
            return image(byteArrayOf(9, 8, 7, 6), digestCharacter = 'b')
        }

        private fun image(bytes: ByteArray, digestCharacter: Char) = InMemoryScreenshot(
            encodedBytes = bytes,
            width = 100,
            height = 200,
            sha256 = digestCharacter.toString().repeat(64),
        )
    }

    private class FakeScreenshotOcrProvider(
        private val blocks: List<OcrTextBlock> = emptyList(),
        private val fail: Boolean = false,
    ) : ScreenshotOcrProvider {
        override suspend fun recognize(source: InMemoryScreenshot): List<OcrTextBlock> {
            if (fail) error("OCR unavailable")
            return blocks
        }

        override fun close() = Unit
    }

    private class FakeHelpRequestSender(
        private val fail: Boolean = false,
    ) : HelpRequestSender {
        var sendCalls = 0
        var lastSubmission: HelpRequestSubmission? = null

        override suspend fun send(submission: HelpRequestSubmission): HelpRequestReceipt {
            sendCalls += 1
            lastSubmission = submission
            if (fail) error("network unavailable")
            return HelpRequestReceipt(
                requestId = "server-request-1",
                clientRequestId = "client-request-1",
                processingRoute = "general_guidance",
                processingStatus = HelpRequestProcessingStatus.RECEIVED,
                statusEndpoint = "/api/v1/help-requests/server-request-1",
            )
        }
    }

    private class FakeHelpRequestStatusReader(
        private val result: HelpRequestResult? = null,
        private val fail: Boolean = false,
    ) : HelpRequestStatusReader {
        var lastRequestId: String? = null

        override suspend fun fetch(requestId: String): HelpRequestResult {
            lastRequestId = requestId
            if (fail) error("status unavailable")
            return requireNotNull(result)
        }
    }
}
