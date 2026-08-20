package com.xisha.guojing.ui.detail

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performClick
import com.xisha.guojing.androidTestDetail
import com.xisha.guojing.execution.ExecutionBlockReason
import com.xisha.guojing.execution.TutorialExecutionEngine
import com.xisha.guojing.execution.TutorialExecutionStage
import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.ui.theme.GuoJingTheme
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class TutorialDetailScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun overview_explains_optional_page_observation_and_starts() {
        var started = false
        composeRule.setContent {
            GuoJingTheme {
                TutorialDetailScreen(
                    uiState = TutorialDetailUiState.Content(androidTestDetail()),
                    onBack = {},
                    onRetry = {},
                    onStartTutorial = { started = true },
                    onConfirmStepCompleted = {},
                    onExitExecution = {},
                )
            }
        }

        composeRule.onNodeWithText("页面观察尚未开启").assertIsDisplayed()
        composeRule.onNodeWithText("开始查看步骤").performClick()

        assertTrue(started)
    }

    @Test
    fun disclosure_requires_affirmative_consent_before_opening_settings() {
        var openedSettings = false
        composeRule.setContent {
            GuoJingTheme {
                TutorialDetailScreen(
                    uiState = TutorialDetailUiState.Content(androidTestDetail()),
                    onBack = {},
                    onRetry = {},
                    onStartTutorial = {},
                    onConfirmStepCompleted = {},
                    onExitExecution = {},
                    onOpenAccessibilitySettings = { openedSettings = true },
                )
            }
        }

        composeRule.onNodeWithText("了解并开启页面观察").performClick()
        composeRule.onNodeWithText("开启前请先了解").assertIsDisplayed()
        composeRule.onNodeWithText("我同意，前往设置").performClick()

        assertTrue(openedSettings)
    }

    @Test
    fun low_risk_step_has_manual_confirmation() {
        val stage = TutorialExecutionEngine(androidTestDetail().graph).start()
            as TutorialExecutionStage.Step
        composeRule.setContent {
            GuoJingTheme {
                TutorialDetailScreen(
                    uiState = TutorialDetailUiState.Content(
                        tutorial = androidTestDetail(),
                        mode = TutorialDetailMode.Execution(stage),
                    ),
                    onBack = {},
                    onRetry = {},
                    onStartTutorial = {},
                    onConfirmStepCompleted = {},
                    onExitExecution = {},
                )
            }
        }

        composeRule.onNodeWithText("第 1 步").assertIsDisplayed()
        composeRule.onNodeWithText("点击“家人”聊天").assertIsDisplayed()
        composeRule.onNodeWithText("我已完成这一步").assertIsDisplayed()
        composeRule.onNodeWithText("页面观察未开启").assertIsDisplayed()
    }

    @Test
    fun matched_local_observation_is_explained_without_exposing_content() {
        val stage = TutorialExecutionEngine(androidTestDetail().graph).start()
            as TutorialExecutionStage.Step
        composeRule.setContent {
            GuoJingTheme {
                TutorialDetailScreen(
                    uiState = TutorialDetailUiState.Content(
                        tutorial = androidTestDetail(),
                        mode = TutorialDetailMode.Execution(
                            stage = stage,
                            pageObservation = PageObservationStatus.Matched(
                                score = 1.0,
                                localOnly = true,
                            ),
                        ),
                    ),
                    onBack = {},
                    onRetry = {},
                    onStartTutorial = {},
                    onConfirmStepCompleted = {},
                    onExitExecution = {},
                    pageObservationServiceEnabled = true,
                )
            }
        }

        composeRule.onNodeWithText("当前页面匹配").assertIsDisplayed()
        composeRule.onNodeWithText("已找到教程需要的页面控件。证据只保留在本机。")
            .assertIsDisplayed()
    }

    @Test
    fun financial_step_is_blocked_without_confirmation_button() {
        val detail = androidTestDetail(riskLevel = RiskLevel.Financial)
        val stage = TutorialExecutionEngine(detail.graph).start()
            as TutorialExecutionStage.Blocked
        assertTrue(stage.reason == ExecutionBlockReason.HighRiskStep)
        composeRule.setContent {
            GuoJingTheme {
                TutorialDetailScreen(
                    uiState = TutorialDetailUiState.Content(
                        tutorial = detail,
                        mode = TutorialDetailMode.Execution(stage),
                    ),
                    onBack = {},
                    onRetry = {},
                    onStartTutorial = {},
                    onConfirmStepCompleted = {},
                    onExitExecution = {},
                )
            }
        }

        composeRule.onNodeWithText("这是高风险操作").assertIsDisplayed()
        assertTrue(
            composeRule.onAllNodesWithText("我已完成这一步")
                .fetchSemanticsNodes().isEmpty(),
        )
    }
}
