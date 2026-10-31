package com.xisha.guojing.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xisha.guojing.session.AgentSessionPort

@Composable
fun GuoJingApp(controller: AgentSessionPort, onOpenAccessibilitySettings: () -> Unit) {
    val model: AgentViewModel = viewModel(factory = AgentViewModel.factory(controller))
    val state by model.uiState.collectAsStateWithLifecycle()
    GuoJingScreen(
        state = state,
        onEntryChanged = model::setEntryEnabled,
        onEnd = model::endSession,
        onOpenAccessibilitySettings = onOpenAccessibilitySettings,
        onInvitationChanged = model::setInvitationDraft,
        onSaveInvitation = model::saveInvitation,
        onInvitationExpanded = model::setInvitationExpanded,
        onRefreshDevice = model::refreshDeviceStatus,
        onConfirmDisableEntry = model::confirmDisableEntry,
        onDismissDisableEntry = model::dismissDisableEntry,
    )
}

@Composable
fun GuoJingScreen(
    state: HomeUiState,
    onEntryChanged: (Boolean) -> Unit,
    onEnd: () -> Unit,
    onOpenAccessibilitySettings: () -> Unit,
    onInvitationChanged: (String) -> Unit = {},
    onSaveInvitation: () -> Unit = {},
    onInvitationExpanded: (Boolean) -> Unit = {},
    onRefreshDevice: () -> Unit = {},
    onConfirmDisableEntry: () -> Unit = {},
    onDismissDisableEntry: () -> Unit = {},
) {
    var focusInvitation by remember { mutableStateOf(false) }
    val invitationLocation = remember { BringIntoViewRequester() }
    val invitationFocus = remember { FocusRequester() }
    val editInvitation: () -> Unit = {
        onInvitationExpanded(true)
        focusInvitation = true
    }
    LaunchedEffect(focusInvitation, state.showInvitationForm) {
        if (focusInvitation && state.showInvitationForm && state.canEditInvitation) {
            invitationLocation.bringIntoView()
            invitationFocus.requestFocus()
            focusInvitation = false
        }
    }
    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).imePadding()
                .testTag("home_scroll").verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(
                Modifier.widthIn(max = 600.dp).fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                HomeHeader()
                if (state.hasSession) {
                    CurrentSessionCard(state.session, onEnd)
                } else {
                    NextStepCard(
                        state = state,
                        onEditInvitation = editInvitation,
                        onOpenSettings = onOpenAccessibilitySettings,
                        onEnableEntry = { onEntryChanged(true) },
                        onRefreshDevice = onRefreshDevice,
                    )
                    state.session.message?.let { HomeMessage(it) }
                }
                PreparationCard(
                    state = state,
                    onEditInvitation = editInvitation,
                    onOpenSettings = onOpenAccessibilitySettings,
                    onEntryChanged = onEntryChanged,
                    invitationContent = {
                        InvitationForm(
                            state, onInvitationChanged, onSaveInvitation,
                            onCancel = { onInvitationExpanded(false) },
                            focusRequester = invitationFocus,
                            modifier = Modifier.bringIntoViewRequester(invitationLocation),
                        )
                    },
                )
                UsageHelp()
                PrivacyNote()
            }
        }
    }
    if (state.confirmDisableEntry) {
        AlertDialog(
            modifier = Modifier.testTag("disable_entry_dialog"),
            onDismissRequest = onDismissDisableEntry,
            title = { Text("关闭悬浮入口？", style = MaterialTheme.typography.titleLarge) },
            text = { Text("关闭后会结束当前指引。需要帮助时，可以在首页重新打开入口。") },
            confirmButton = {
                TextButton(onClick = onConfirmDisableEntry) { Text("关闭并结束指引") }
            },
            dismissButton = {
                TextButton(onClick = onDismissDisableEntry) { Text("继续本次指引") }
            },
        )
    }
}

@Composable
internal fun HomePrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(16.dp),
        modifier = modifier.fillMaxWidth().heightIn(min = 56.dp),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 14.dp),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}
