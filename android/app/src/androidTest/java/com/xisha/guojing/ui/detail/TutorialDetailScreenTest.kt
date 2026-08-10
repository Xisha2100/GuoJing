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
    fun overview_explains_demo_mode_and_starts() {
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

        composeRule.onNodeWithText("当前是演示模式").assertIsDisplayed()
        composeRule.onNodeWithText("开始查看步骤").performClick()

        assertTrue(started)
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
