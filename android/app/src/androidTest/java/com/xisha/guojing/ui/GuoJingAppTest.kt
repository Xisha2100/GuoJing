package com.xisha.guojing.ui

import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import com.xisha.guojing.model.TargetApp
import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.ClientPhase
import com.xisha.guojing.ui.theme.GuoJingTheme
import org.junit.Rule
import org.junit.Test

class GuoJingAppTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun setup_explains_cloud_upload_and_blocks_start_without_consent() {
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    state = readyState(uploadConsent = false),
                    onGoalChanged = {}, onAppSelected = {}, onConsentChanged = {},
                    onStart = {}, onOpenTarget = {}, onRetry = {}, onEnd = {},
                    onOpenAccessibilitySettings = {},
                )
            }
        }

        compose.onNodeWithText("当前目标应用截图会发送到配置的云端智能体", substring = true)
            .assertExists()
        compose.onNodeWithContentDescription("开始界面指引").assertIsNotEnabled()
    }

    @Test
    fun valid_setup_allows_start() {
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    state = readyState(uploadConsent = true),
                    onGoalChanged = {}, onAppSelected = {}, onConsentChanged = {},
                    onStart = {}, onOpenTarget = {}, onRetry = {}, onEnd = {},
                    onOpenAccessibilitySettings = {},
                )
            }
        }

        compose.onNodeWithContentDescription("开始界面指引").assertIsEnabled()
    }

    private fun readyState(uploadConsent: Boolean) = AgentClientUiState(
        phase = ClientPhase.Setup,
        availableApps = listOf(TargetApp("com.tencent.mm", "微信")),
        selectedPackage = "com.tencent.mm",
        goal = "找到扫一扫",
        uploadConsent = uploadConsent,
        accessibilityConnected = true,
    )
}
