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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
    pageObservationServiceEnabled: Boolean = false,
    onOpenAccessibilitySettings: () -> Unit = {},
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
                        pageObservationServiceEnabled = pageObservationServiceEnabled,
                        onOpenAccessibilitySettings = onOpenAccessibilitySettings,
                    )
                    is TutorialDetailMode.Execution -> TutorialExecution(
                        stage = mode.stage,
                        pageObservation = mode.pageObservation,
                        transitionVerification = mode.transitionVerification,
                        pageObservationServiceEnabled = pageObservationServiceEnabled,
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
    pageObservationServiceEnabled: Boolean,
    onOpenAccessibilitySettings: () -> Unit,
) {
    var showDisclosure by remember { mutableStateOf(false) }
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
            body = "每次只显示一个操作。开启页面观察后，老牌子会跨 APP 框选目标，并在你操作后确认结果。",
        )
        if (pageObservationServiceEnabled) {
            InfoCard(
                title = "页面观察已开启",
                body = "开始教程后，老牌子只在本机识别目标 APP 的页面控件，不会替你点击。",
                emphasized = true,
            )
        } else {
            InfoCard(
                title = "页面观察尚未开启",
                body = "不开启也能查看步骤；开启后，老牌子可以在本地提示当前页面是否匹配。",
                emphasized = true,
            )
            OutlinedButton(
                onClick = { showDisclosure = true },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
            ) {
                Text("了解并开启页面观察")
            }
        }
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
    if (showDisclosure) {
        PageObservationDisclosure(
            onDismiss = { showDisclosure = false },
            onConsent = {
                showDisclosure = false
                onOpenAccessibilitySettings()
            },
        )
    }
}

@Composable
private fun TutorialExecution(
    stage: TutorialExecutionStage,
    pageObservation: PageObservationStatus,
    transitionVerification: TransitionVerificationStatus,
    pageObservationServiceEnabled: Boolean,
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
            is TutorialExecutionStage.Step -> StepContent(
                stage = stage,
                pageObservation = pageObservation,
                transitionVerification = transitionVerification,
                pageObservationServiceEnabled = pageObservationServiceEnabled,
                onConfirmStepCompleted = onConfirmStepCompleted,
            )
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
    pageObservation: PageObservationStatus,
    transitionVerification: TransitionVerificationStatus,
    pageObservationServiceEnabled: Boolean,
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
    PageObservationNotice(pageObservation, pageObservationServiceEnabled)
    TransitionVerificationNotice(transitionVerification, pageObservationServiceEnabled)
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
        enabled = !pageObservationServiceEnabled ||
            transitionVerification == TransitionVerificationStatus.Ready,
        modifier = Modifier
            .fillMaxWidth()
            .height(60.dp),
    ) {
        Text(
            if (pageObservationServiceEnabled) {
                "我已操作，切回目标 APP 确认"
            } else {
                "我已完成这一步（手动）"
            },
        )
    }
}

@Composable
private fun TransitionVerificationNotice(
    status: TransitionVerificationStatus,
    serviceEnabled: Boolean,
) {
    if (!serviceEnabled || status == TransitionVerificationStatus.Ready) return
    val (title, body) = when (status) {
        TransitionVerificationStatus.Ready -> return
        is TransitionVerificationStatus.CheckingTarget -> "正在确认操作结果" to
            "已获得 ${status.matchedObservations}/${status.requiredObservations} 次稳定页面证据。请不要重复操作。"
        TransitionVerificationStatus.TargetUncertain -> "结果还不够确定" to
            "老牌子会继续观察目标页面。请等待，不要再次点击同一个按钮。"
        TransitionVerificationStatus.TargetMismatch -> "没有到达预期页面" to
            "请不要重复操作；返回教程要求的页面，或退出本次教程。"
        TransitionVerificationStatus.CapturePaused -> "目标页面禁止观察" to
            "页面可能包含密码或验证码，老牌子已停止读取，也不会自动完成这一步。"
    }
    InfoCard(title = title, body = body, emphasized = true)
}

@Composable
private fun PageObservationNotice(
    status: PageObservationStatus,
    serviceEnabled: Boolean,
) {
    val (title, body) = when {
        !serviceEnabled -> "页面观察未开启" to "你仍可手动查看步骤，但老牌子无法确认当前页面。"
        status == PageObservationStatus.NotStarted ->
            "页面观察正在准备" to "打开教程对应的 APP 后，老牌子才会读取页面证据。"
        status == PageObservationStatus.WaitingForTargetApp ->
            "等待目标 APP" to "请切换到教程对应的 APP；其他 APP 的页面不会被读取。"
        status == PageObservationStatus.CapturePaused ->
            "页面观察已暂停" to "这个步骤可能包含密码或验证码，老牌子不会读取页面节点。"
        status is PageObservationStatus.Matched -> {
            val privacy = if (status.localOnly) "证据只保留在本机。" else "只生成脱敏后的锚点证据。"
            "当前页面匹配" to "已找到教程需要的页面控件。$privacy"
        }
        status is PageObservationStatus.VersionChanged ->
            "APP 版本有变化" to "页面看起来匹配，但教程是在其他版本确认的。仅允许低风险步骤试运行，并等待下一页再次确认。"
        status == PageObservationStatus.VersionStale ->
            "教程版本已过期" to "这个教程节点已标记为过期，老牌子不会继续显示引导。"
        status is PageObservationStatus.Uncertain ->
            "暂时无法确认页面" to "页面控件不够完整，请检查是否打开了正确页面。"
        status == PageObservationStatus.Mismatch ->
            "当前页面不匹配" to "请不要继续重复操作，先返回教程要求的页面。"
        else -> error("unhandled page observation status")
    }
    InfoCard(
        title = title,
        body = body,
        emphasized = status !is PageObservationStatus.Matched,
    )
}

@Composable
private fun PageObservationDisclosure(
    onDismiss: () -> Unit,
    onConsent: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("开启前请先了解") },
        text = {
            Text(
                "页面观察会在你主动运行教程时读取目标 APP 的按钮、文字标签和控件位置，" +
                    "用于判断当前页面是否与教程一致。老牌子不会替你点击，不会读取密码控件，" +
                    "也不会保存完整页面内容；标记为“仅本地”的证据不会上传。你可以随时在系统设置中关闭。",
            )
        },
        confirmButton = {
            Button(onClick = onConsent) {
                Text("我同意，前往设置")
            }
        },
        dismissButton = {
            OutlinedButton(onClick = onDismiss) {
                Text("暂不开启")
            }
        },
    )
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
