package com.xisha.guojing.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xisha.guojing.session.AgentClientUiState
import com.xisha.guojing.session.AgentSessionController
import com.xisha.guojing.session.ClientPhase

@Composable
fun GuoJingApp(controller: AgentSessionController, onOpenAccessibilitySettings: () -> Unit) {
    val model: AgentViewModel = viewModel(factory = AgentViewModel.factory(controller))
    val state by model.uiState.collectAsStateWithLifecycle()
    GuoJingScreen(state, model::setEntryEnabled, model::endSession, onOpenAccessibilitySettings)
}

@Composable
fun GuoJingScreen(
    state: AgentClientUiState,
    onEntryChanged: (Boolean) -> Unit,
    onEnd: () -> Unit,
    onOpenAccessibilitySettings: () -> Unit,
) {
    Scaffold { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            Text("老牌子", style = MaterialTheme.typography.headlineLarge)
            Text("在你正在使用的应用里，随时开始指引。")
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(if (state.accessibilityConnected) "界面指引服务已连接" else "请先开启界面指引服务")
                    if (!state.accessibilityConnected) {
                        Button(onClick = onOpenAccessibilitySettings) { Text("去开启") }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        Text("显示悬浮入口", Modifier.weight(1f))
                        Switch(state.entryEnabled, onCheckedChange = onEntryChanged)
                    }
                }
            }
            Text("1. 打开你想操作的应用。\n2. 点击屏幕边缘的“帮我”按钮。\n3. 输入目标，点击“开始指引”。")
            Text("每次开始或继续识别，都会上传当前应用截图。你可以随时取消或结束。")
            if (state.phase != ClientPhase.Setup) {
                Text("当前指引：" + (state.targetLabel ?: "正在创建"))
                state.instruction?.let { Text(it) }
                Button(onClick = onEnd) { Text("结束本次指引") }
            }
            state.message?.let { Text(it) }
        }
    }
}
