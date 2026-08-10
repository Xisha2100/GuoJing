package com.xisha.guojing.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.xisha.guojing.execution.ExecutionBlockReason
import com.xisha.guojing.execution.TutorialExecutionStage
import com.xisha.guojing.model.ActionKind
import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.model.VerificationStatus

@Composable
fun TutorialDetailScreen(
    uiState: TutorialDetailUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onStartTutorial: () -> Unit,
    onConfirmStepCompleted: () -> Unit,
    onExitExecution: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.safeDrawing),
        ) {
            DetailTopBar(onBack)
            when (uiState) {
                TutorialDetailUiState.Loading -> DetailLoading()
                TutorialDetailUiState.Error -> DetailError(onRetry)
                is TutorialDetailUiState.Content -> when (val mode = uiState.mode) {
                    TutorialDetailMode.Overview -> TutorialOverview(
                        uiState = uiState,
                        onStartTutorial = onStartTutorial,
                    )
                    is TutorialDetailMode.Execution -> TutorialExecution(
                        stage = mode.stage,
                        onConfirmStepCompleted = onConfirmStepCompleted,
                        onExitExecution = onExitExecution,
                    )
                }
            }
        }
    }
}

@Composable
private fun DetailTopBar(onBack: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        OutlinedButton(
            onClick = onBack,
            modifier = Modifier.height(52.dp),
        ) {
            Text("返回")
        }
        Text(
            text = "教程详情",
            modifier = Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
        )
    }
}

@Composable
private fun TutorialOverview(
    uiState: TutorialDetailUiState.Content,
    onStartTutorial: () -> Unit,
) {
    val tutorial = uiState.tutorial
    val graph = tutorial.graph
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text(
            text = graph.title,
            modifier = Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineLarge,
        )
        Text(
            text = "录制版本：${graph.recordedApp.versionName}",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyLarge,
        )
        InfoCard(
            title = "这个教程怎样工作？",
            body = "每次只显示一个操作。你亲自完成后，再点击“我已完成这一步”。",
        )
        InfoCard(
            title = "当前是演示模式",
            body = "老牌子还没有自动观察其他 APP 的页面，因此现在不会判断你是否点对了位置。",
            emphasized = true,
        )
        Text(
            text = "共 ${graph.transitions.size} 个已录制操作，教程修订 ${tutorial.revisionNumber}",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyMedium,
        )
        Button(
            onClick = onStartTutorial,
            modifier = Modifier
                .fillMaxWidth()
                .height(60.dp),
        ) {
            Text("开始查看步骤")
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun TutorialExecution(
    stage: TutorialExecutionStage,
    onConfirmStepCompleted: () -> Unit,
    onExitExecution: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        when (stage) {
            is TutorialExecutionStage.Step -> StepContent(stage, onConfirmStepCompleted)
            is TutorialExecutionStage.Completed -> CompletedContent(stage)
            is TutorialExecutionStage.Blocked -> BlockedContent(stage)
        }
        OutlinedButton(
            onClick = onExitExecution,
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
        ) {
            Text(
                if (stage is TutorialExecutionStage.Completed) {
                    "返回教程详情"
                } else {
                    "退出本次教程"
                },
            )
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun StepContent(
    stage: TutorialExecutionStage.Step,
    onConfirmStepCompleted: () -> Unit,
) {
    Text(
        text = "第 ${stage.stepNumber} 步",
        color = MaterialTheme.colorScheme.primary,
        style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.Bold,
    )
    Text(
        text = stage.transition.instruction,
        modifier = Modifier.semantics { heading() },
        style = MaterialTheme.typography.headlineLarge,
    )
    Text(
        text = "当前页面：${stage.node.title}",
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodyLarge,
    )
    InfoCard(
        title = "操作方式",
        body = stage.transition.actionKind.userFacingLabel(),
    )
    PrivacyNotice(stage.node.privacyMode)
    if (stage.node.verificationStatus == VerificationStatus.Provisional) {
        InfoCard(
            title = "这个页面仍在复核",
            body = "APP 更新后页面可能发生变化；如果界面不一样，请退出教程。",
            emphasized = true,
        )
    }
    if (stage.transition.riskLevel == RiskLevel.Sensitive) {
        InfoCard(
            title = "这是敏感操作",
            body = "请先确认联系人或输入内容正确，再亲自操作。",
            emphasized = true,
        )
    }
    Button(
        onClick = onConfirmStepCompleted,
        modifier = Modifier
            .fillMaxWidth()
            .height(60.dp),
    ) {
        Text("我已完成这一步")
    }
}

@Composable
private fun CompletedContent(stage: TutorialExecutionStage.Completed) {
    Text(
        text = "教程已完成",
        modifier = Modifier.semantics { heading() },
        style = MaterialTheme.typography.headlineLarge,
    )
    Text(
        text = "已经到达：${stage.node.title}",
        style = MaterialTheme.typography.bodyLarge,
    )
    InfoCard(
        title = "做得很好",
        body = "本次共查看 ${stage.completedTransitionIds.size} 个操作步骤。",
    )
}

@Composable
private fun BlockedContent(stage: TutorialExecutionStage.Blocked) {
    Text(
        text = "教程已安全暂停",
        modifier = Modifier.semantics { heading() },
        style = MaterialTheme.typography.headlineLarge,
    )
    InfoCard(
        title = stage.reason.blockedTitle(),
        body = stage.reason.blockedMessage(),
        emphasized = true,
    )
    if (stage.reason == ExecutionBlockReason.HighRiskStep && stage.transition != null) {
        Text(
            text = "被暂停的操作：${stage.transition.instruction}",
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun PrivacyNotice(privacyMode: PrivacyMode) {
    val message = when (privacyMode) {
        PrivacyMode.NetworkAllowed -> "这个页面允许使用经过脱敏的在线识别。"
        PrivacyMode.LocalOnly -> "这个页面可能包含隐私，后续识别必须只在手机本地完成。"
        PrivacyMode.CapturePaused -> "这个页面禁止截图和识别；密码、验证码等内容需要你亲自处理。"
    }
    InfoCard(
        title = "隐私提示",
        body = message,
        emphasized = privacyMode != PrivacyMode.NetworkAllowed,
    )
}

@Composable
private fun InfoCard(
    title: String,
    body: String,
    emphasized: Boolean = false,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (emphasized) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surface
            },
        ),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleLarge,
            )
            Text(
                text = body,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
    }
}

@Composable
private fun DetailLoading() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator(
                modifier = Modifier.size(48.dp),
                strokeWidth = 5.dp,
            )
            Spacer(Modifier.height(18.dp))
            Text("正在读取教程……", style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun DetailError(onRetry: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(28.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            Text(
                text = "无法读取这个教程",
                modifier = Modifier.semantics { heading() },
                style = MaterialTheme.typography.headlineSmall,
                textAlign = TextAlign.Center,
            )
            Text(
                text = "教程可能已撤回，或者网络暂时不可用。",
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
            )
            Button(
                onClick = onRetry,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
            ) {
                Text("重新加载")
            }
        }
    }
}

private fun ActionKind.userFacingLabel(): String = when (this) {
    ActionKind.Tap -> "轻点一次"
    ActionKind.Hold -> "按住不放"
    ActionKind.Scroll -> "用手指滑动页面"
    ActionKind.Input -> "输入文字"
    ActionKind.Wait -> "等待页面变化"
    ActionKind.SystemBack -> "使用手机的返回操作"
}

private fun ExecutionBlockReason.blockedTitle(): String = when (this) {
    ExecutionBlockReason.StaleNode -> "录制页面已经过期"
    ExecutionBlockReason.AmbiguousBranch -> "这里存在多条操作路线"
    ExecutionBlockReason.HighRiskStep -> "这是高风险操作"
    ExecutionBlockReason.CycleRequiresObservation -> "这一步需要识别页面后再继续"
    ExecutionBlockReason.InvalidGraph -> "教程数据不完整"
}

private fun ExecutionBlockReason.blockedMessage(): String = when (this) {
    ExecutionBlockReason.StaleNode -> "当前版本不能确认页面仍然一致，请等待管理员复核。"
    ExecutionBlockReason.AmbiguousBranch -> "当前演示模式不能安全判断应该选择哪条路线。"
    ExecutionBlockReason.HighRiskStep -> "支付或不可逆操作暂不继续引导，请让可信家属陪同处理。"
    ExecutionBlockReason.CycleRequiresObservation -> "重复步骤必须先确认手机当前页面，演示模式不能自行判断。"
    ExecutionBlockReason.InvalidGraph -> "为了避免给出错误操作，老牌子已经停止这个教程。"
}
