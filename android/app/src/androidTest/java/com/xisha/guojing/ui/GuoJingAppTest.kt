package com.xisha.guojing.ui

import android.content.Context
import android.graphics.Bitmap
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.ClientPhase
import com.xisha.guojing.session.DeviceSetupState
import com.xisha.guojing.ui.theme.GuoJingTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class GuoJingAppTest {
    @get:Rule val compose = createComposeRule()

    @Test
    fun first_use_shows_local_invitation_form_without_app_picker_or_capture_action() {
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    HomeUiState(session = AgentClientUiState(deviceSetup = DeviceSetupState.MissingInvitation)),
                    {}, {}, {},
                )
            }
        }

        compose.onNodeWithText("老牌子").assertIsDisplayed()
        compose.onNodeWithTag("invitation_input").assertExists()
        compose.onNodeWithTag("invitation_save").assertIsNotEnabled()
        compose.onNodeWithText("选择要操作的应用").assertDoesNotExist()
        compose.onNodeWithText("开始识别").assertDoesNotExist()
        compose.onNodeWithTag("privacy_note").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun saved_invitation_is_collapsed_and_permission_is_the_next_action() {
        var opened = 0
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    HomeUiState(session = AgentClientUiState(deviceSetup = DeviceSetupState.InvitationSaved)),
                    {}, {}, { opened += 1 },
                )
            }
        }

        compose.onNodeWithTag("invitation_input").assertDoesNotExist()
        compose.onNodeWithText("去开启指引服务").performScrollTo().performClick()
        compose.runOnIdle { assertEquals(1, opened) }
        compose.onNodeWithTag("invitation_edit").assertIsEnabled()
    }

    @Test
    fun ready_home_changes_when_service_disconnects_or_entry_is_hidden() {
        var state by mutableStateOf(readyHome())
        var enabled: Boolean? = null
        compose.setContent {
            GuoJingTheme { GuoJingScreen(state, { enabled = it }, {}, {}) }
        }

        compose.onNodeWithText("可以开始使用了").assertExists()
        compose.onNodeWithTag("invitation_input").assertDoesNotExist()
        compose.runOnIdle {
            state = state.copy(session = state.session.copy(accessibilityConnected = false))
        }
        compose.onNodeWithText("去开启指引服务").assertExists()
        compose.runOnIdle {
            state = state.copy(session = state.session.copy(accessibilityConnected = true, entryEnabled = false))
        }
        compose.onNodeWithText("打开悬浮入口").performScrollTo().performClick()
        compose.runOnIdle { assertEquals(true, enabled) }
    }

    @Test
    fun device_loading_failure_can_be_retried_without_starting_a_session() {
        var state by mutableStateOf(HomeUiState())
        var refreshed = 0
        var ended = 0
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    state, {}, { ended += 1 }, {},
                    onRefreshDevice = { refreshed += 1 },
                )
            }
        }
        compose.onNodeWithTag("session_card").assertDoesNotExist()
        compose.runOnIdle {
            state = state.copy(session = state.session.copy(deviceSetup = DeviceSetupState.Failed("无法读取本机资料")))
        }
        compose.onNodeWithText("重试读取").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(1, refreshed)
            assertEquals(0, ended)
        }
    }

    @Test
    fun changing_invitation_expands_form_and_failure_preserves_the_draft() {
        var state by mutableStateOf(readyHome())
        var saves = 0
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    state, {}, {}, {},
                    onInvitationChanged = { state = state.copy(invitationDraft = it, invitationError = null) },
                    onInvitationExpanded = { state = state.copy(invitationExpanded = it) },
                    onSaveInvitation = {
                        saves += 1
                        state = state.copy(invitationError = "保存失败，请重试")
                    },
                )
            }
        }

        compose.onNodeWithTag("invitation_edit").performScrollTo().performClick()
        compose.onNodeWithTag("invitation_input").performScrollTo().performTextInput(TEST_INVITATION)
        compose.onNodeWithTag("invitation_save").performScrollTo().performClick()
        compose.onNodeWithText("保存失败，请重试", substring = true).assertExists()
        compose.runOnIdle {
            assertEquals(TEST_INVITATION, state.invitationDraft)
            assertEquals(1, saves)
        }
    }

    @Test
    fun saving_disables_repeat_submission_and_success_collapses_the_form() {
        var state by mutableStateOf(readyHome().copy(invitationExpanded = true, invitationDraft = TEST_INVITATION))
        var saves = 0
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    state, {}, {}, {},
                    onSaveInvitation = {
                        saves += 1
                        state = state.copy(invitationSaving = true)
                    },
                )
            }
        }
        compose.onNodeWithTag("invitation_save").performScrollTo().performClick()
        compose.onNodeWithTag("invitation_save").assertIsNotEnabled()
        compose.onNodeWithTag("invitation_input").assertIsNotEnabled()
        compose.runOnIdle {
            assertEquals(1, saves)
            assertEquals(TEST_INVITATION, state.invitationDraft)
            state = state.copy(
                session = state.session.copy(deviceSetup = DeviceSetupState.InvitationSaved),
                invitationDraft = "", invitationExpanded = false,
                invitationSaving = false, invitationSaved = true,
            )
        }
        compose.onNodeWithTag("invitation_input").assertDoesNotExist()
        compose.onNodeWithTag("invitation_edit").assertIsEnabled()
    }

    @Test
    fun every_session_phase_prioritizes_task_and_prevents_invitation_changes() {
        var state by mutableStateOf(readyHome())
        var ends = 0
        compose.setContent {
            GuoJingTheme { GuoJingScreen(state, {}, { ends += 1 }, {}) }
        }
        for (phase in ClientPhase.entries.filter { it != ClientPhase.Setup }) {
            compose.runOnIdle {
                state = state.copy(session = state.session.copy(
                    phase = phase, targetLabel = "示例应用", goal = "打开设置",
                    instruction = if (phase == ClientPhase.ShowingGuidance) COMPLETE_INSTRUCTION else null,
                    message = if (phase == ClientPhase.Retry) "网络暂时不可用，请返回目标应用后重试" else null,
                ))
            }
            compose.onNodeWithTag("session_card").performScrollTo().assertIsDisplayed()
            val taskTop = compose.onNodeWithTag("session_card").fetchSemanticsNode().positionInRoot.y
            val preparationTop = compose.onNodeWithTag("preparation_card").fetchSemanticsNode().positionInRoot.y
            assertTrue("Task must precede setup for $phase", taskTop < preparationTop)
            compose.onNodeWithTag("invitation_edit").assertIsNotEnabled()
            compose.onNodeWithText("请先结束当前指引，再更换邀请码").assertExists()
            if (phase == ClientPhase.ShowingGuidance) {
                compose.onNodeWithText(COMPLETE_INSTRUCTION).assertExists()
            }
            if (phase == ClientPhase.Retry) {
                compose.onNodeWithText("网络暂时不可用，请返回目标应用后重试", substring = true).assertExists()
            }
        }
        compose.onNodeWithText("结束本次指引").performScrollTo().performClick()
        compose.runOnIdle { assertEquals(1, ends) }
    }

    @Test
    fun previous_instruction_is_hidden_while_waiting_for_new_screen_evidence() {
        var state by mutableStateOf(readyHome().copy(session = readyHome().session.copy(
            phase = ClientPhase.ShowingGuidance,
            instruction = COMPLETE_INSTRUCTION,
        )))
        compose.setContent {
            GuoJingTheme { GuoJingScreen(state, {}, {}, {}) }
        }
        compose.onNodeWithText(COMPLETE_INSTRUCTION).assertExists()

        for (phase in listOf(
            ClientPhase.Capturing,
            ClientPhase.WaitingForAgent,
            ClientPhase.ReadyToCapture,
            ClientPhase.Retry,
        )) {
            compose.runOnIdle { state = state.copy(session = state.session.copy(phase = phase)) }
            // The old instruction deliberately remains in state: rendering must follow the phase.
            compose.onNodeWithText(COMPLETE_INSTRUCTION).assertDoesNotExist()
        }

        compose.runOnIdle {
            state = state.copy(session = state.session.copy(phase = ClientPhase.Completed))
        }
        compose.onNodeWithText(COMPLETE_INSTRUCTION).assertExists()
    }

    @Test
    fun closing_entry_during_session_requires_confirmation_and_can_be_cancelled() {
        var state by mutableStateOf(readyHome().copy(session = readyHome().session.copy(phase = ClientPhase.ShowingGuidance)))
        var confirmations = 0
        var dismissals = 0
        compose.setContent {
            GuoJingTheme {
                GuoJingScreen(
                    state,
                    onEntryChanged = { if (!it) state = state.copy(confirmDisableEntry = true) },
                    onEnd = {}, onOpenAccessibilitySettings = {},
                    onConfirmDisableEntry = {
                        confirmations += 1
                        state = state.copy(confirmDisableEntry = false, session = state.session.copy(entryEnabled = false))
                    },
                    onDismissDisableEntry = {
                        dismissals += 1
                        state = state.copy(confirmDisableEntry = false)
                    },
                )
            }
        }
        compose.onNodeWithTag("entry_toggle").performScrollTo().performClick()
        compose.onNodeWithTag("disable_entry_dialog").assertExists()
        compose.onNodeWithText("继续本次指引").performClick()
        compose.onNodeWithTag("disable_entry_dialog").assertDoesNotExist()
        compose.onNodeWithTag("entry_toggle").assertIsOn()
        compose.runOnIdle {
            assertEquals(0, confirmations)
            assertEquals(1, dismissals)
        }
        compose.onNodeWithTag("entry_toggle").performClick()
        compose.onNode(hasText("关闭并结束指引") and hasClickAction()).performClick()
        compose.runOnIdle { assertEquals(1, confirmations) }
    }

    @Test
    fun full_instruction_and_actions_remain_accessible_in_narrow_large_font_and_landscape_viewports() {
        var landscape by mutableStateOf(false)
        val state = readyHome().copy(session = readyHome().session.copy(
            phase = ClientPhase.ShowingGuidance, targetLabel = "示例应用",
            instruction = COMPLETE_INSTRUCTION,
        ))
        compose.setContent {
            TestViewport(fontScale = 2f, landscape = landscape) {
                GuoJingScreen(state, {}, {}, {})
            }
        }
        for (isLandscape in listOf(false, true)) {
            compose.runOnIdle { landscape = isLandscape }
            val layouts = mutableListOf<TextLayoutResult>()
            compose.onNodeWithText(COMPLETE_INSTRUCTION).performScrollTo().performSemanticsAction(
                SemanticsActions.GetTextLayoutResult,
            ) { it(layouts) }
            assertTrue(layouts.isNotEmpty())
            assertTrue(layouts.all { it.layoutInput.text.text == COMPLETE_INSTRUCTION })
            assertFalse("Instruction must wrap without ellipsis", layouts.any { it.hasVisualOverflow })
            compose.onNodeWithText("结束本次指引").performScrollTo().assertIsDisplayed()
            compose.onNodeWithTag("entry_toggle").performScrollTo().assertIsDisplayed()
            compose.onNodeWithTag("privacy_note").performScrollTo().assertIsDisplayed()
        }
    }

    @Test
    fun capture_home_previews_for_visual_review() {
        var scale by mutableStateOf(1f)
        compose.setContent {
            TestViewport(fontScale = scale, narrow = false) {
                GuoJingScreen(
                    HomeUiState(session = AgentClientUiState(deviceSetup = DeviceSetupState.InvitationSaved)),
                    {}, {}, {},
                )
            }
        }
        savePreview("home-normal.png")
        compose.runOnIdle { scale = 2f }
        // Return to the summary after changing the typography scale.
        compose.onNodeWithText("老牌子").performScrollTo()
        savePreview("home-large-font.png")
    }

    private fun savePreview(name: String) {
        compose.waitForIdle()
        val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.openFileOutput(name, Context.MODE_PRIVATE).use { output ->
            assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output))
        }
    }

    companion object {
        private val TEST_INVITATION = "test_invitation_" + "a".repeat(32)
        private const val COMPLETE_INSTRUCTION = "点击右上角的设置按钮，确认显示的是个人设置后再继续，不要点击退出登录。"

        private fun readyHome() = HomeUiState(session = AgentClientUiState(
            deviceSetup = DeviceSetupState.Activated, accessibilityConnected = true, entryEnabled = true,
        ))
    }
}

@Composable
private fun TestViewport(
    fontScale: Float,
    landscape: Boolean = false,
    narrow: Boolean = true,
    content: @Composable () -> Unit,
) {
    val density = LocalDensity.current
    CompositionLocalProvider(LocalDensity provides Density(density.density, fontScale)) {
        GuoJingTheme {
            BoxWithConstraints(Modifier.fillMaxSize()) {
                val width = when {
                    landscape -> minOf(600.dp, maxWidth)
                    narrow -> minOf(320.dp, maxWidth)
                    else -> maxWidth
                }
                val height = if (landscape) 240.dp else maxHeight
                Box(Modifier.width(width).height(height)) { content() }
            }
        }
    }
}
