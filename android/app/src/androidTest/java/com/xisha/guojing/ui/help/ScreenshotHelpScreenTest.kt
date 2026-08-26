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
import com.xisha.guojing.privacy.ScreenshotSanitizationReceipt
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
