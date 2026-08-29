package com.xisha.guojing.ui.help

import android.graphics.Bitmap
import android.graphics.Color
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.data.HelpRequestIntent
import com.xisha.guojing.data.HelpRequestProcessingStatus
import com.xisha.guojing.data.HelpRequestReceipt
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.OcrPrivacySuggestion
import com.xisha.guojing.privacy.PrivacySuggestionDecision
import com.xisha.guojing.privacy.ScreenshotSanitizationReceipt
import com.xisha.guojing.privacy.SensitiveTextKind
import com.xisha.guojing.ui.theme.GuoJingTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.io.ByteArrayOutputStream

class ScreenshotHelpScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun awaiting_screen_explains_local_only_intake_before_picker() {
        var pickerOpened = false
        composeRule.setContent {
            GuoJingTheme {
                ScreenshotHelpScreen(
                    uiState = ScreenshotHelpUiState.AwaitingSelection(),
                    onBack = {},
                    onPickScreenshot = { pickerOpened = true },
                    onQuestionChanged = {},
                    onAddRedaction = {},
                    onUndoRedaction = {},
                    onNoSensitiveContentChanged = {},
                    onSanitize = {},
                )
            }
        }

        composeRule.onNodeWithText("先保护隐私").assertIsDisplayed()
        composeRule.onNodeWithText("现在不会发送").assertIsDisplayed()
        composeRule.onNodeWithText("选择一张截图").performClick()

        assertTrue(pickerOpened)
    }

    @Test
    fun editing_requires_question_and_privacy_confirmation() {
        var question by mutableStateOf("")
        var confirmed by mutableStateOf(false)
        var sanitized = false
        val screenshot = testScreenshot()
        composeRule.setContent {
            GuoJingTheme {
                ScreenshotHelpScreen(
                    uiState = ScreenshotHelpUiState.Editing(
                        screenshot = screenshot,
                        question = question,
                        noSensitiveContentConfirmed = confirmed,
                    ),
                    onBack = {},
                    onPickScreenshot = {},
                    onQuestionChanged = { question = it },
                    onAddRedaction = {},
                    onUndoRedaction = {},
                    onNoSensitiveContentChanged = { confirmed = it },
                    onSanitize = { sanitized = true },
                )
            }
        }

        composeRule.onNodeWithText("添加遮挡区域").performClick()
        composeRule.onNodeWithText("现在请在截图上拖动")
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("生成脱敏副本")
            .performScrollTo()
            .assertIsNotEnabled()
        composeRule.onNodeWithTag("screenshot_question_input")
            .performTextInput("下一步怎么做？")
        composeRule.onNodeWithText("我已检查，截图中没有隐私内容")
            .performScrollTo()
            .performClick()

        assertEquals("下一步怎么做？", question)
        assertTrue(confirmed)
        assertTrue(!sanitized)
    }

    @Test
    fun editing_requires_explicit_decision_for_ocr_privacy_suggestions() {
        var suggestions by mutableStateOf(
            listOf(
                OcrPrivacySuggestion(
                    id = "ocr-suggestion-1",
                    kind = SensitiveTextKind.Phone,
                    bounds = requireNotNull(
                        NormalizedRedaction.fromDrag(0.1f, 0.2f, 0.8f, 0.3f),
                    ),
                    confidence = 0.95,
                ),
            ),
        )
        val screenshot = testScreenshot()
        composeRule.setContent {
            GuoJingTheme {
                ScreenshotHelpScreen(
                    uiState = ScreenshotHelpUiState.Editing(
                        screenshot = screenshot,
                        question = "这个电话是什么？",
                        privacySuggestions = suggestions,
                    ),
                    onBack = {},
                    onPickScreenshot = {},
                    onQuestionChanged = {},
                    onAddRedaction = {},
                    onUndoRedaction = {},
                    onNoSensitiveContentChanged = {},
                    onSanitize = {},
                    onAcceptPrivacySuggestion = { id ->
                        suggestions = suggestions.map { suggestion ->
                            if (suggestion.id == id) {
                                suggestion.copy(decision = PrivacySuggestionDecision.Accepted)
                            } else {
                                suggestion
                            }
                        }
                    },
                    onRejectPrivacySuggestion = {},
                )
            }
        }

        composeRule.onNodeWithText("本机发现的可能隐私").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("可能是电话号码").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("生成脱敏副本").performScrollTo().assertIsNotEnabled()
        composeRule.onNodeWithText("遮住这处").performScrollTo().performClick()
        composeRule.onNodeWithText("已加入黑色遮挡区域").assertIsDisplayed()
    }

    @Test
    fun ready_screen_never_claims_that_ai_has_received_the_image() {
        composeRule.setContent {
            GuoJingTheme {
                ScreenshotHelpScreen(
                    uiState = ScreenshotHelpUiState.Ready(
                        screenshot = testScreenshot(),
                        question = "这里应该点哪里？",
                        receipt = ScreenshotSanitizationReceipt(
                            redactionCount = 2,
                            noSensitiveContentConfirmed = false,
                            sanitizedSha256 = "c".repeat(64),
                        ),
                    ),
                    onBack = {},
                    onPickScreenshot = {},
                    onQuestionChanged = {},
                    onAddRedaction = {},
                    onUndoRedaction = {},
                    onNoSensitiveContentChanged = {},
                    onSanitize = {},
                )
            }
        }

        composeRule.onNodeWithText("脱敏副本已准备好").assertIsDisplayed()
        composeRule.onNodeWithText("尚未发送给 AI").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("已经永久遮挡 2 处；脱敏副本校验码 cccccccccccc。")
            .assertIsDisplayed()
    }

    @Test
    fun ready_screen_requires_explicit_send_consent() {
        composeRule.setContent {
            GuoJingTheme {
                ScreenshotHelpScreen(
                    uiState = ScreenshotHelpUiState.Ready(
                        screenshot = testScreenshot(),
                        question = "这里应该点哪里？",
                        receipt = ScreenshotSanitizationReceipt(
                            redactionCount = 1,
                            noSensitiveContentConfirmed = false,
                            sanitizedSha256 = "d".repeat(64),
                        ),
                    ),
                    onBack = {},
                    onPickScreenshot = {},
                    onQuestionChanged = {},
                    onAddRedaction = {},
                    onUndoRedaction = {},
                    onNoSensitiveContentChanged = {},
                    onSanitize = {},
                )
            }
        }

        composeRule.onNodeWithText("第三步：选择帮助方式").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("查找已录制教程")
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("我确认只发送这份已经脱敏的截图和问题")
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("发送脱敏副本")
            .performScrollTo()
            .assertIsNotEnabled()
    }

    @Test
    fun submitted_screen_explains_processing_status_and_allows_refresh() {
        var refreshed = false
        composeRule.setContent {
            GuoJingTheme {
                ScreenshotHelpScreen(
                    uiState = ScreenshotHelpUiState.Submitted(
                        question = "这里应该点哪里？",
                        receipt = ScreenshotSanitizationReceipt(
                            redactionCount = 1,
                            noSensitiveContentConfirmed = false,
                            sanitizedSha256 = "e".repeat(64),
                        ),
                        intent = HelpRequestIntent.GENERAL_GUIDANCE,
                        serverReceipt = HelpRequestReceipt(
                            requestId = "server-request-1",
                            clientRequestId = "client-request-1",
                            processingRoute = "general_guidance",
                            processingStatus = HelpRequestProcessingStatus.RECEIVED,
                            statusEndpoint = "/api/v1/help-requests/server-request-1",
                        ),
                    ),
                    onBack = {},
                    onPickScreenshot = {},
                    onQuestionChanged = {},
                    onAddRedaction = {},
                    onUndoRedaction = {},
                    onNoSensitiveContentChanged = {},
                    onSanitize = {},
                    onRefreshStatus = { refreshed = true },
                )
            }
        }

        composeRule.onNodeWithText("当前处理状态")
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("已接收，正在等待处理。")
            .performScrollTo()
            .assertIsDisplayed()
        composeRule.onNodeWithText("刷新处理状态")
            .performScrollTo()
            .performClick()

        assertTrue(refreshed)
    }

    private fun testScreenshot(): InMemoryScreenshot {
        val bitmap = Bitmap.createBitmap(20, 30, Bitmap.Config.ARGB_8888).apply {
            eraseColor(Color.WHITE)
        }
        val bytes = ByteArrayOutputStream().use { output ->
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
            output.toByteArray()
        }
        bitmap.recycle()
        return InMemoryScreenshot(
            encodedBytes = bytes,
            width = 20,
            height = 30,
            sha256 = "a".repeat(64),
        )
    }
}
