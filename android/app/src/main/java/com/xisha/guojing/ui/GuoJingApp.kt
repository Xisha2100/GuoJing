package com.xisha.guojing.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xisha.guojing.model.TargetApp
import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.AgentSessionController
import com.xisha.guojing.session.ClientPhase

@Composable
fun GuoJingApp(
    controller: AgentSessionController,
    onOpenAccessibilitySettings: () -> Unit,
) {
    val viewModel: AgentViewModel = viewModel(factory = AgentViewModel.factory(controller))
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    GuoJingScreen(
        state = state,
        onGoalChanged = viewModel::updateGoal,
        onAppSelected = viewModel::selectApp,
        onConsentChanged = viewModel::setUploadConsent,
        onStart = viewModel::startSession,
        onOpenTarget = viewModel::openTargetApp,
        onRetry = viewModel::requestGuidance,
        onEnd = viewModel::endSession,
        onOpenAccessibilitySettings = onOpenAccessibilitySettings,
    )
}

@Composable
fun GuoJingScreen(
    state: AgentClientUiState,
    onGoalChanged: (String) -> Unit,
    onAppSelected: (String) -> Unit,
    onConsentChanged: (Boolean) -> Unit,
    onStart: () -> Unit,
    onOpenTarget: () -> Unit,
    onRetry: () -> Unit,
    onEnd: () -> Unit,
    onOpenAccessibilitySettings: () -> Unit,
) {
    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("老牌子", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
            Text("看懂当前界面，一步一步带你完成操作", style = MaterialTheme.typography.bodyLarge)
            AccessibilityCard(state.accessibilityConnected, onOpenAccessibilitySettings)
            if (state.phase in setOf(ClientPhase.Setup, ClientPhase.CreatingSession)) {
                SetupContent(state, onGoalChanged, onAppSelected, onConsentChanged, onStart)
            } else {
                ActiveContent(state, onOpenTarget, onRetry, onEnd)
            }
        }
    }
}

@Composable
private fun AccessibilityCard(connected: Boolean, onOpenSettings: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text("界面指引服务", fontWeight = FontWeight.Bold)
                Text(if (connected) "已连接，可以截图和显示指引" else "未开启，请先在系统中授权")
            }
            if (!connected) Button(onClick = onOpenSettings) { Text("去开启") }
        }
    }
}

@Composable
private fun SetupContent(
    state: AgentClientUiState,
    onGoalChanged: (String) -> Unit,
    onAppSelected: (String) -> Unit,
    onConsentChanged: (Boolean) -> Unit,
    onStart: () -> Unit,
) {
    var choosingApp by remember { mutableStateOf(false) }
    val selected = state.availableApps.firstOrNull { it.packageName == state.selectedPackage }
    OutlinedButton(onClick = { choosingApp = true }, modifier = Modifier.fillMaxWidth()) {
        Text(selected?.let { "目标应用：${it.label}" } ?: "选择要操作的应用")
    }
    OutlinedTextField(
        value = state.goal,
        onValueChange = onGoalChanged,
        modifier = Modifier.fillMaxWidth(),
        label = { Text("你想完成什么？") },
        placeholder = { Text("例如：帮我找到微信扫一扫") },
        minLines = 3,
        maxLines = 5,
        enabled = state.phase == ClientPhase.Setup,
    )
    Row(
        modifier = Modifier.fillMaxWidth().clickable {
            onConsentChanged(!state.uploadConsent)
        },
        verticalAlignment = Alignment.Top,
    ) {
        Checkbox(checked = state.uploadConsent, onCheckedChange = onConsentChanged)
        Text(
            "我知道：每次点击悬浮按钮时，当前目标应用截图会发送到配置的云端智能体。应用不会自动点击或操作手机。",
            modifier = Modifier.padding(top = 10.dp),
        )
    }
    state.message?.let { ErrorText(it) }
    Button(
        onClick = onStart,
        enabled = state.canStart,
        modifier = Modifier.fillMaxWidth().semantics { contentDescription = "开始界面指引" },
    ) {
        if (state.phase == ClientPhase.CreatingSession) {
            CircularProgressIndicator(modifier = Modifier.height(20.dp), strokeWidth = 2.dp)
        } else {
            Text("开始指引")
        }
    }
    if (choosingApp) {
        AppChooser(
            apps = state.availableApps,
            onSelected = {
                onAppSelected(it.packageName)
                choosingApp = false
            },
            onDismiss = { choosingApp = false },
        )
    }
}

@Composable
private fun ActiveContent(
    state: AgentClientUiState,
    onOpenTarget: () -> Unit,
    onRetry: () -> Unit,
    onEnd: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(state.targetLabel ?: "目标应用", fontWeight = FontWeight.Bold)
            Text(phaseLabel(state.phase), style = MaterialTheme.typography.titleLarge)
            state.instruction?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
            state.confidence?.let { Text("识别置信度 ${(it * 100).toInt()}%") }
            state.message?.let { ErrorText(it) }
        }
    }
    Text("切换到目标应用后，通过悬浮按钮开始识别。每点击一次，只上传当前这一帧截图。")
    Button(onClick = onOpenTarget, modifier = Modifier.fillMaxWidth()) { Text("打开目标应用") }
    if (state.phase == ClientPhase.Retry) {
        Button(onClick = onRetry, modifier = Modifier.fillMaxWidth()) { Text("重新识别") }
    }
    OutlinedButton(onClick = onEnd, modifier = Modifier.fillMaxWidth()) { Text("结束本次指引") }
}

@Composable
private fun AppChooser(
    apps: List<TargetApp>,
    onSelected: (TargetApp) -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("选择目标应用") },
        text = {
            LazyColumn {
                items(apps, key = TargetApp::packageName) { app ->
                    Column(
                        modifier = Modifier.fillMaxWidth().clickable { onSelected(app) }
                            .padding(vertical = 14.dp),
                    ) {
                        Text(app.label, fontWeight = FontWeight.Bold)
                        Text(app.packageName, style = MaterialTheme.typography.bodySmall)
                    }
                    HorizontalDivider()
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

@Composable
private fun ErrorText(message: String) {
    Text(message, color = MaterialTheme.colorScheme.error)
}

private fun phaseLabel(phase: ClientPhase): String = when (phase) {
    ClientPhase.Setup -> "准备开始"
    ClientPhase.CreatingSession -> "正在创建会话"
    ClientPhase.ReadyToCapture -> "等待你点击悬浮按钮"
    ClientPhase.Capturing -> "正在截取当前界面"
    ClientPhase.WaitingForAgent -> "智能体正在分析"
    ClientPhase.ShowingGuidance -> "当前操作位置已标出"
    ClientPhase.Retry -> "需要重新识别"
    ClientPhase.Completed -> "目标已完成"
}
