package com.xisha.guojing.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.ClientPhase
import com.xisha.guojing.session.DeviceSetupState
import com.xisha.guojing.ui.theme.WarmHighlight

@Composable
internal fun HomeHeader() {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            "老牌子", color = MaterialTheme.colorScheme.primary,
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.semantics { heading() },
        )
        Text(
            "手机操作，一步一步来。", style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
internal fun HomeCard(
    modifier: Modifier = Modifier,
    highlighted: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (highlighted) WarmHighlight else MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(
            Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp),
            content = content,
        )
    }
}

@Composable
internal fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() })
}

@Composable
internal fun NextStepCard(
    state: HomeUiState,
    onEditInvitation: () -> Unit,
    onOpenSettings: () -> Unit,
    onEnableEntry: () -> Unit,
    onRefreshDevice: () -> Unit,
) {
    val action = nextPreparation(state.session)
    HomeCard(Modifier.testTag("next_step_card"), highlighted = true) {
        Surface(
            shape = RoundedCornerShape(50), color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.primary,
        ) {
            Text(
                if (action == PreparationAction.Ready) "准备就绪" else "使用准备",
                Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        val title = when (action) {
            PreparationAction.Loading -> "正在读取本机资料"
            PreparationAction.Invitation -> "先保存你的邀请码"
            PreparationAction.Accessibility -> if (state.session.entryEnabled) {
                "再完成一步，就能使用"
            } else "接下来，开启指引服务"
            PreparationAction.Entry -> "打开入口，随时获得帮助"
            PreparationAction.Ready -> "可以开始使用了"
            PreparationAction.Blocked -> "需要处理开通问题"
            PreparationAction.Failed -> "暂时无法读取资料"
        }
        Text(
            title, style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.semantics { heading(); liveRegion = LiveRegionMode.Polite },
        )
        Text(
            when (action) {
                PreparationAction.Loading -> "正在检查已保存的邀请码与开通状态。"
                PreparationAction.Invitation -> "输入邀请人提供的邀请码，只需在本机保存一次。"
                PreparationAction.Accessibility -> "在系统设置中找到“老牌子”，开启界面指引服务。"
                PreparationAction.Entry -> "开启后，屏幕边缘会显示“帮我”按钮。"
                PreparationAction.Ready -> "打开需要帮助的应用，点击屏幕边缘的“帮我”。"
                PreparationAction.Blocked, PreparationAction.Failed ->
                    devicePreparationLabel(state.session.deviceSetup)
            },
            style = MaterialTheme.typography.bodyLarge,
        )
        when (action) {
            PreparationAction.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            PreparationAction.Invitation -> if (!state.showInvitationForm) {
                HomePrimaryButton("填写邀请码", onEditInvitation)
            }
            PreparationAction.Accessibility -> HomePrimaryButton("去开启指引服务", onOpenSettings)
            PreparationAction.Entry -> HomePrimaryButton("打开悬浮入口", onEnableEntry)
            PreparationAction.Failed -> HomePrimaryButton("重试读取", onRefreshDevice)
            PreparationAction.Blocked -> HomePrimaryButton("更换邀请码", onEditInvitation)
            PreparationAction.Ready -> if (state.session.deviceSetup == DeviceSetupState.InvitationSaved) {
                Text(
                    "邀请码已保存，首次确认目标时联网激活。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
internal fun HomeMessage(message: String, modifier: Modifier = Modifier) {
    Surface(
        modifier.semantics { liveRegion = LiveRegionMode.Polite },
        color = MaterialTheme.colorScheme.errorContainer,
        contentColor = MaterialTheme.colorScheme.onErrorContainer,
        shape = RoundedCornerShape(12.dp),
    ) {
        Text("提示：$message", Modifier.padding(12.dp), style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
internal fun CurrentSessionCard(state: AgentClientUiState, onEnd: () -> Unit) {
    HomeCard(Modifier.testTag("session_card"), highlighted = true) {
        Text("当前指引", color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodyMedium)
        SectionTitle(when (state.phase) {
            ClientPhase.Setup -> "准备开始"
            ClientPhase.CreatingSession -> "正在准备指引"
            ClientPhase.ReadyToCapture -> "回到目标应用后继续"
            ClientPhase.Capturing -> "正在获取当前界面"
            ClientPhase.WaitingForAgent -> "正在识别，请稍候"
            ClientPhase.ShowingGuidance -> "第 ${state.stepNumber} 步"
            ClientPhase.Retry -> "本次指引需要重试"
            ClientPhase.Completed -> "本次目标已完成"
        })
        state.targetLabel?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        if (state.goal.isNotBlank()) Text("目标：${state.goal}", style = MaterialTheme.typography.bodyMedium)
        state.message?.let { HomeMessage(it) }
        if (state.phase in setOf(ClientPhase.ShowingGuidance, ClientPhase.Completed)) {
            state.instruction?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
        }
        if (state.phase in setOf(ClientPhase.CreatingSession, ClientPhase.Capturing, ClientPhase.WaitingForAgent)) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
        }
        if (state.phase in setOf(ClientPhase.ReadyToCapture, ClientPhase.ShowingGuidance, ClientPhase.Retry)) {
            Text(
                "请回到目标应用，使用悬浮按钮继续。", style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        OutlinedButton(onClick = onEnd, modifier = Modifier.fillMaxWidth()) {
            Text("结束本次指引", modifier = Modifier.padding(vertical = 8.dp))
        }
    }
}

@Composable
internal fun UsageHelp() {
    var expanded by rememberSaveable { mutableStateOf(false) }
    HomeCard {
        SectionTitle("如何开始")
        HelpStep("1", "打开需要帮助的应用")
        HelpStep("2", "点击屏幕边缘的“帮我”")
        TextButton(onClick = { expanded = !expanded }) {
            Text(if (expanded) "收起使用说明" else "查看详细使用说明")
        }
        if (expanded) {
            Text(
                "输入你想完成的目标，点击“开始指引”。每次只提示一步，请自己完成操作；点击下一步后，才会重新识别当前界面。你可以随时取消或结束。",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun HelpStep(number: String, text: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(number, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.titleLarge)
        Text(text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
    }
}

@Composable
internal fun PrivacyNote() {
    Text(
        "只有确认目标或点击下一步后，才会上传当前截图。应用不会替你点击或操作手机。",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.testTag("privacy_note").padding(horizontal = 4.dp, vertical = 4.dp),
    )
}
