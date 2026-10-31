package com.xisha.guojing.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.error
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.xisha.guojing.session.DeviceSetupState

@Composable
internal fun PreparationCard(
    state: HomeUiState,
    onEditInvitation: () -> Unit,
    onOpenSettings: () -> Unit,
    onEntryChanged: (Boolean) -> Unit,
    invitationContent: @Composable () -> Unit,
) {
    val session = state.session
    HomeCard(Modifier.testTag("preparation_card")) {
        SectionTitle("准备事项")
        PreparationRow(
            marker = if (session.deviceSetup == DeviceSetupState.Activated ||
                session.deviceSetup == DeviceSetupState.InvitationSaved) "✓" else "1",
            title = "邀请码",
            detail = devicePreparationLabel(session.deviceSetup),
        )
        if (state.showInvitationForm) {
            invitationContent()
        } else {
            TextButton(
                onClick = onEditInvitation,
                enabled = state.canEditInvitation,
                modifier = Modifier.testTag("invitation_edit"),
            ) { Text("更换邀请码") }
        }
        if (state.hasSession) {
            Text(
                "请先结束当前指引，再更换邀请码", style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (state.invitationSaved) {
            Text(
                "邀请码已保存", color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        PreparationRow(
            marker = if (session.accessibilityConnected) "✓" else "2",
            title = "界面指引服务",
            detail = if (session.accessibilityConnected) "已连接" else "待开启",
        )
        // The hero owns the primary settings action; retain access during a session
        // or when another preparation step currently has priority.
        if (!session.accessibilityConnected &&
            (state.hasSession || nextPreparation(session) != PreparationAction.Accessibility)) {
            TextButton(onClick = onOpenSettings) { Text("前往系统设置") }
        }
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        Row(
            Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("entry_toggle")
                .semantics { stateDescription = if (session.entryEnabled) "已打开" else "已关闭" }
                .toggleable(session.entryEnabled, role = Role.Switch, onValueChange = onEntryChanged),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("悬浮入口", style = MaterialTheme.typography.bodyLarge)
                Text(
                    if (session.entryEnabled) "已打开" else "已关闭",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(checked = session.entryEnabled, onCheckedChange = null)
        }
    }
}

@Composable
private fun PreparationRow(marker: String, title: String, detail: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
        Surface(
            shape = CircleShape,
            color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.primary,
        ) {
            androidx.compose.foundation.layout.Box(
                Modifier.sizeIn(minWidth = 40.dp, minHeight = 40.dp).padding(8.dp)
                    .clearAndSetSemantics { },
                contentAlignment = Alignment.Center,
            ) {
                Text(marker, style = MaterialTheme.typography.bodyMedium)
            }
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(detail, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
internal fun InvitationForm(
    state: HomeUiState,
    onChanged: (String) -> Unit,
    onSave: () -> Unit,
    onCancel: () -> Unit,
    focusRequester: FocusRequester,
    modifier: Modifier = Modifier,
) {
    val focus = LocalFocusManager.current
    val canSubmit = state.canEditInvitation && state.invitationDraft.isNotBlank()
    val submit: () -> Unit = {
        if (canSubmit) {
            focus.clearFocus()
            onSave()
        }
    }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedTextField(
            value = state.invitationDraft,
            onValueChange = onChanged,
            label = { Text("请输入邀请码", style = MaterialTheme.typography.bodyMedium) },
            textStyle = MaterialTheme.typography.bodyLarge,
            singleLine = true,
            enabled = state.canEditInvitation,
            isError = state.invitationError != null,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                autoCorrectEnabled = false, keyboardType = KeyboardType.Password, imeAction = ImeAction.Done,
            ),
            keyboardActions = KeyboardActions(onDone = { submit() }),
            modifier = Modifier.fillMaxWidth().testTag("invitation_input").focusRequester(focusRequester)
                .semantics { state.invitationError?.let { error(it) } },
        )
        state.invitationError?.let { HomeMessage(it) }
        HomePrimaryButton(
            if (state.invitationSaving) "正在保存…" else "保存邀请码",
            onClick = submit,
            enabled = canSubmit,
            modifier = Modifier.testTag("invitation_save"),
        )
        Text(
            "仅加密保存在本机，此时不会联网。首次确认目标时激活；卸载重装需要重新邀请。",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (state.session.deviceSetup != DeviceSetupState.MissingInvitation) {
            TextButton(onClick = onCancel, enabled = !state.invitationSaving) { Text("收起") }
        }
    }
}
