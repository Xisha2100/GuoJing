package com.xisha.guojing.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.waitUntilAtLeastOneExists
import com.xisha.guojing.androidTestDetail
import com.xisha.guojing.androidTestSummary
import com.xisha.guojing.data.TutorialCatalogRepository
import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.ui.theme.GuoJingTheme
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalTestApi::class)
class GuoJingAppTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun catalog_navigates_through_linear_tutorial_to_completion() {
        composeRule.setContent {
            GuoJingTheme {
                GuoJingApp(
                    catalogRepository = TutorialCatalogRepository {
                        listOf(androidTestSummary)
                    },
                    detailRepository = TutorialDetailRepository {
                        androidTestDetail()
                    },
                )
            }
        }

        composeRule.waitUntilAtLeastOneExists(hasText("查看步骤"))
        composeRule.onNodeWithText("查看步骤").performClick()
        composeRule.waitUntilAtLeastOneExists(hasText("开始查看步骤"))
        composeRule.onNodeWithText("教程详情").assertIsDisplayed()

        composeRule.onNodeWithText("开始查看步骤").performClick()
        composeRule.onNodeWithText("点击“家人”聊天").assertIsDisplayed()

        composeRule.onNodeWithText("我已完成这一步（手动）").performClick()
        composeRule.onNodeWithText("教程已完成").assertIsDisplayed()
    }

    @Test
    fun catalog_opens_screenshot_help_without_requiring_a_tutorial() {
        composeRule.setContent {
            GuoJingTheme {
                GuoJingApp(
                    catalogRepository = TutorialCatalogRepository { emptyList() },
                    detailRepository = TutorialDetailRepository { androidTestDetail() },
                )
            }
        }

        composeRule.onNodeWithText("截图问一问").performClick()
        composeRule.onNodeWithText("哪里不会，就截哪里").assertIsDisplayed()
        composeRule.onNodeWithText("现在不会发送").assertIsDisplayed()
    }
}
