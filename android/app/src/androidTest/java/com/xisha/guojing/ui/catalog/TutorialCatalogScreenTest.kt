package com.xisha.guojing.ui.catalog

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.xisha.guojing.model.TutorialSummary
import com.xisha.guojing.ui.theme.GuoJingTheme
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class TutorialCatalogScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun content_displays_published_tutorial() {
        composeRule.setContent {
            GuoJingTheme {
                TutorialCatalogScreen(
                    uiState = TutorialCatalogUiState.Content(listOf(TUTORIAL)),
                    onRetry = {},
                )
            }
        }

        composeRule.onNodeWithText("可以学习的教程").assertIsDisplayed()
        composeRule.onNodeWithText("微信打电话").assertIsDisplayed()
        composeRule.onNodeWithText("适用于 8.0.60 版本").assertIsDisplayed()
    }

    @Test
    fun error_allows_retry() {
        var retried = false
        composeRule.setContent {
            GuoJingTheme {
                TutorialCatalogScreen(
                    uiState = TutorialCatalogUiState.Error,
                    onRetry = { retried = true },
                )
            }
        }

        composeRule.onNodeWithText("重新加载").performClick()

        assertTrue(retried)
    }

    private companion object {
        val TUTORIAL = TutorialSummary(
            graphId = "wechat-call",
            title = "微信打电话",
            packageName = "com.tencent.mm",
            recordedVersionName = "8.0.60",
            recordedVersionCode = 2800,
            revisionNumber = 3,
            publishedAt = "2026-08-09T07:00:00Z",
        )
    }
}
