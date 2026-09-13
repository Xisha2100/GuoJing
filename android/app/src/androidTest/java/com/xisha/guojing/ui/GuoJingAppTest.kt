package com.xisha.guojing.ui

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.ui.theme.GuoJingTheme
import org.junit.Rule
import org.junit.Test
import org.junit.Assert.assertTrue

class GuoJingAppTest {
    @get:Rule val compose = createComposeRule()

    @Test
    fun home_explains_floating_entry_without_app_selection() {
        compose.setContent {
            GuoJingTheme { GuoJingScreen(AgentClientUiState(), {}, {}, {}) }
        }
        compose.onNodeWithText("选择要操作的应用").assertDoesNotExist()
        compose.onNodeWithText("请先开启界面指引服务").assertExists()
        compose.onNodeWithText("显示悬浮入口").assertExists()
    }

    @Test
    fun permission_button_opens_settings_callback() {
        var opened = false
        compose.setContent {
            GuoJingTheme { GuoJingScreen(AgentClientUiState(), {}, {}, { opened = true }) }
        }
        compose.onNodeWithText("去开启").performClick()
        assertTrue(opened)
    }
}
