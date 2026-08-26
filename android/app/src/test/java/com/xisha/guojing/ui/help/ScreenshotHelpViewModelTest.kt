package com.xisha.guojing.ui.help

import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.ScreenshotPrivacyProcessor
import com.xisha.guojing.data.HelpRequestIntent
import com.xisha.guojing.data.HelpRequestReceipt
import com.xisha.guojing.data.HelpRequestSender
import com.xisha.guojing.data.HelpRequestSubmission
import com.xisha.guojing.ui.catalog.MainDispatcherRule
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
                processingStatus = "accepted_no_model",
            )
        }
    }
}
