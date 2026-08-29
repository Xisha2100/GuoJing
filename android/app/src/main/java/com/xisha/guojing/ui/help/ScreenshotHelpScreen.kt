package com.xisha.guojing.ui.help

import android.graphics.BitmapFactory
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.xisha.guojing.data.HelpRequestIntent
import com.xisha.guojing.data.HelpRequestProcessingStatus
import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.OcrPrivacySuggestion
import com.xisha.guojing.privacy.PrivacySuggestionDecision

@Composable
fun ScreenshotHelpScreen(
    uiState: ScreenshotHelpUiState,
    onBack: () -> Unit,
    onPickScreenshot: () -> Unit,
    onQuestionChanged: (String) -> Unit,
    onAddRedaction: (NormalizedRedaction) -> Unit,
    onUndoRedaction: () -> Unit,
    onNoSensitiveContentChanged: (Boolean) -> Unit,
    onSanitize: () -> Unit,
    onIntentSelected: (HelpRequestIntent) -> Unit = {},
    onSendConsentChanged: (Boolean) -> Unit = {},
    onSend: () -> Unit = {},
    onRefreshStatus: () -> Unit = {},
    onAcceptPrivacySuggestion: (String) -> Unit = {},
    onRejectPrivacySuggestion: (String) -> Unit = {},
) {
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.safeDrawing),
        ) {
            ScreenshotHelpHeader(onBack)
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                when (uiState) {
                    is ScreenshotHelpUiState.AwaitingSelection -> AwaitingContent(
                        error = uiState.error,
                        onPickScreenshot = onPickScreenshot,
                    )
                    ScreenshotHelpUiState.Importing -> BusyContent("正在本机读取截图……")
                    is ScreenshotHelpUiState.Editing -> EditingContent(
                        state = uiState,
                        onPickScreenshot = onPickScreenshot,
                        onQuestionChanged = onQuestionChanged,
                        onAddRedaction = onAddRedaction,
                        onUndoRedaction = onUndoRedaction,
                        onNoSensitiveContentChanged = onNoSensitiveContentChanged,
                        onSanitize = onSanitize,
                        onAcceptPrivacySuggestion = onAcceptPrivacySuggestion,
                        onRejectPrivacySuggestion = onRejectPrivacySuggestion,
                    )
                    is ScreenshotHelpUiState.Sanitizing -> {
                        ScreenshotPreview(
                            screenshot = uiState.screenshot,
                            redactions = uiState.redactions,
                            contentDescription = "正在本机处理的截图",
                        )
                        BusyContent("正在本机生成脱敏副本……")
                    }
                    is ScreenshotHelpUiState.Ready -> ReadyContent(
                        state = uiState,
                        onPickScreenshot = onPickScreenshot,
                        onIntentSelected = onIntentSelected,
                        onSendConsentChanged = onSendConsentChanged,
                        onSend = onSend,
                    )
                    is ScreenshotHelpUiState.Sending -> BusyContent("正在发送脱敏副本……")
                    is ScreenshotHelpUiState.Submitted -> SubmittedContent(
                        state = uiState,
                        onPickScreenshot = onPickScreenshot,
                        onRefreshStatus = onRefreshStatus,
                    )
                }
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@Composable
private fun ScreenshotHelpHeader(onBack: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TextButton(onClick = onBack) {
            Text("返回")
        }
        Text(
            text = "截图问一问",
            modifier = Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
        )
    }
}

@Composable
private fun AwaitingContent(
    error: ScreenshotHelpError?,
    onPickScreenshot: () -> Unit,
) {
    Text(
        text = "哪里不会，就截哪里",
        modifier = Modifier.semantics { heading() },
        style = MaterialTheme.typography.headlineMedium,
    )
    InfoCard(
        title = "先保护隐私",
        body = "选择截图后，请用手指框住姓名、头像、电话、地址、余额、订单号和二维码。老牌子会先在手机里生成遮挡副本。",
    )
    InfoCard(
        title = "现在不会发送",
        body = "本机 OCR 只用于给你提示可能的隐私区域。原图和 OCR 原文都不会上传；视觉模型和 Agent 还没有接入。",
    )
    if (error == ScreenshotHelpError.ImportFailed) {
        ErrorCard("无法读取这张图片，请重新选择一张截图。")
    }
    Button(
        onClick = onPickScreenshot,
        modifier = Modifier
            .fillMaxWidth()
            .height(60.dp),
    ) {
        Text("选择一张截图")
    }
}

@Composable
private fun EditingContent(
    state: ScreenshotHelpUiState.Editing,
    onPickScreenshot: () -> Unit,
    onQuestionChanged: (String) -> Unit,
    onAddRedaction: (NormalizedRedaction) -> Unit,
    onUndoRedaction: () -> Unit,
    onNoSensitiveContentChanged: (Boolean) -> Unit,
    onSanitize: () -> Unit,
    onAcceptPrivacySuggestion: (String) -> Unit,
    onRejectPrivacySuggestion: (String) -> Unit,
) {
    var addingRedaction by remember(state.screenshot) { mutableStateOf(false) }
    Text(
        text = "第一步：遮住隐私",
        modifier = Modifier.semantics { heading() },
        style = MaterialTheme.typography.headlineSmall,
    )
    Text(
        text = "每次点击“添加遮挡区域”，再在截图上按住并拖动。黑色区域会在脱敏副本中永久遮住。",
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodyLarge,
    )
    OutlinedButton(
        onClick = { addingRedaction = !addingRedaction },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(if (addingRedaction) "取消本次框选" else "添加遮挡区域")
    }
    if (addingRedaction) {
        InfoCard(
            title = "现在请在截图上拖动",
            body = "完成一处框选后会自动退出框选模式，避免影响上下滑动页面。",
        )
    }
    ScreenshotPreview(
        screenshot = state.screenshot,
        redactions = state.redactions,
        suggestions = state.privacySuggestions.filter {
            it.decision == PrivacySuggestionDecision.Pending
        },
        contentDescription = "待脱敏截图",
        onAddRedaction = if (addingRedaction) {
            { redaction ->
                onAddRedaction(redaction)
                addingRedaction = false
            }
        } else {
            null
        },
    )
    if (state.privacySuggestions.isNotEmpty()) {
        PrivacySuggestionSection(
            suggestions = state.privacySuggestions,
            onAccept = onAcceptPrivacySuggestion,
            onReject = onRejectPrivacySuggestion,
        )
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "已遮挡 ${state.redactions.size} 处",
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.Bold,
        )
        OutlinedButton(
            onClick = onUndoRedaction,
            enabled = state.redactions.isNotEmpty(),
        ) {
            Text("撤销上一处")
        }
    }
    if (state.redactions.isEmpty() && state.privacySuggestions.none {
            it.decision == PrivacySuggestionDecision.Pending
        }
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .toggleable(
                    value = state.noSensitiveContentConfirmed,
                    role = Role.Checkbox,
                    onValueChange = onNoSensitiveContentChanged,
                )
                .semantics(mergeDescendants = true) {},
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(
                checked = state.noSensitiveContentConfirmed,
                onCheckedChange = null,
            )
            Text(
                text = "我已检查，截图中没有隐私内容",
                style = MaterialTheme.typography.bodyLarge,
            )
        }
    }
    Text(
        text = "第二步：说清楚哪里不会",
        modifier = Modifier.semantics { heading() },
        style = MaterialTheme.typography.headlineSmall,
    )
    OutlinedTextField(
        value = state.question,
        onValueChange = onQuestionChanged,
        modifier = Modifier
            .fillMaxWidth()
            .testTag(QUESTION_INPUT_TEST_TAG),
        minLines = 3,
        maxLines = 5,
        label = { Text("例如：下一步应该点哪里？") },
        supportingText = { Text("${state.question.length}/300") },
    )
    if (state.error == ScreenshotHelpError.SanitizationFailed) {
        ErrorCard("脱敏副本生成失败，原图仍只在本次内存会话中，可以重试。")
    }
    if (state.error == ScreenshotHelpError.OcrFailed) {
        ErrorCard("本机文字识别没有完成，你仍可以手动框选隐私区域。")
    }
    if (state.error == ScreenshotHelpError.OcrSuggestionsTruncated) {
        ErrorCard("这张截图中的隐私提示过多，无法完整确认。请缩小截图范围后重新选择。")
    }
    if (state.privacySuggestions.any {
            it.decision == PrivacySuggestionDecision.Pending
        }
    ) {
        InfoCard(
            title = "请先处理文字识别建议",
            body = "每一条建议都要选择“遮住这处”或“不是隐私”，确认后才能生成脱敏副本。",
        )
    }
    Button(
        onClick = onSanitize,
        enabled = state.canSanitize,
        modifier = Modifier
            .fillMaxWidth()
            .height(60.dp),
    ) {
        Text("生成脱敏副本")
    }
    OutlinedButton(
        onClick = onPickScreenshot,
        modifier = Modifier
            .fillMaxWidth()
            .height(56.dp),
    ) {
        Text("换一张截图")
    }
}

private const val QUESTION_INPUT_TEST_TAG = "screenshot_question_input"

@Composable
private fun PrivacySuggestionSection(
    suggestions: List<OcrPrivacySuggestion>,
    onAccept: (String) -> Unit,
    onReject: (String) -> Unit,
) {
    InfoCard(
        title = "本机发现的可能隐私",
        body = "这些只是识别建议，不会自动遮挡。请逐条确认，橙色框表示还没有决定。",
    )
    suggestions.forEach { suggestion ->
        val decision = suggestion.decision
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceContainer,
            ),
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = "可能是${suggestion.kind.displayName}",
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = "本机识别把握约 ${(suggestion.confidence * 100).toInt()}%",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )
                when (decision) {
                    PrivacySuggestionDecision.Pending -> Row(
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Button(onClick = { onAccept(suggestion.id) }) {
                            Text("遮住这处")
                        }
                        OutlinedButton(onClick = { onReject(suggestion.id) }) {
                            Text("不是隐私")
                        }
                    }
                    PrivacySuggestionDecision.Accepted -> Text(
                        text = "已加入黑色遮挡区域",
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    PrivacySuggestionDecision.Rejected -> Text(
                        text = "已忽略这条建议",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyLarge,
                    )
                }
            }
        }
    }
}

@Composable
private fun ReadyContent(
    state: ScreenshotHelpUiState.Ready,
    onPickScreenshot: () -> Unit,
    onIntentSelected: (HelpRequestIntent) -> Unit,
    onSendConsentChanged: (Boolean) -> Unit,
    onSend: () -> Unit,
) {
    Text(
        text = "脱敏副本已准备好",
        modifier = Modifier.semantics { heading() },
        color = MaterialTheme.colorScheme.primary,
        style = MaterialTheme.typography.headlineMedium,
    )
    ScreenshotPreview(screenshot = state.screenshot)
    InfoCard(
        title = "你的问题",
        body = state.question,
    )
    InfoCard(
        title = "本地处理记录",
        body = if (state.receipt.redactionCount > 0) {
            "已经永久遮挡 ${state.receipt.redactionCount} 处；脱敏副本校验码 ${state.receipt.sanitizedSha256.take(12)}。"
        } else {
            "你确认截图没有隐私内容；脱敏副本校验码 ${state.receipt.sanitizedSha256.take(12)}。"
        },
    )
    InfoCard(
        title = "尚未发送给 AI",
        body = "当前只完成了本地脱敏和本机 OCR 建议。OCR 原文不会发送；视觉模型和基础指引 Agent 还没有接入。",
    )
    Text(
        text = "第三步：选择帮助方式",
        modifier = Modifier.semantics { heading() },
        style = MaterialTheme.typography.headlineSmall,
    )
    IntentChoice(
        selected = state.intent == HelpRequestIntent.RECORDED_TUTORIAL,
        title = "查找已录制教程",
        body = "如果老牌子已有这个 APP 的教程，优先尝试匹配。",
        onClick = { onIntentSelected(HelpRequestIntent.RECORDED_TUTORIAL) },
    )
    IntentChoice(
        selected = state.intent == HelpRequestIntent.GENERAL_GUIDANCE,
        title = "没有教程，先看基础指引",
        body = "适用于尚未录制的 APP，后续只生成解释，不自动替你操作。",
        onClick = { onIntentSelected(HelpRequestIntent.GENERAL_GUIDANCE) },
    )
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .toggleable(
                value = state.sendConsent,
                role = Role.Checkbox,
                onValueChange = onSendConsentChanged,
            )
            .semantics(mergeDescendants = true) {},
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(
            checked = state.sendConsent,
            onCheckedChange = null,
        )
        Text(
            text = "我确认只发送这份已经脱敏的截图和问题",
            style = MaterialTheme.typography.bodyLarge,
        )
    }
    if (state.error == ScreenshotHelpError.SendFailed) {
        ErrorCard("发送失败，脱敏副本仍只在本次内存会话中，可以重试。")
    }
    Button(
        onClick = onSend,
        enabled = state.canSend,
        modifier = Modifier
            .fillMaxWidth()
            .height(60.dp),
    ) {
        Text("发送脱敏副本")
    }
    Button(
        onClick = onPickScreenshot,
        modifier = Modifier
            .fillMaxWidth()
            .height(60.dp),
    ) {
        Text("重新选择截图")
    }
}

@Composable
private fun IntentChoice(
    selected: Boolean,
    title: String,
    body: String,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .selectable(
                selected = selected,
                role = Role.RadioButton,
                onClick = onClick,
            )
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.Top,
    ) {
        RadioButton(
            selected = selected,
            onClick = null,
        )
        Column(
            modifier = Modifier.padding(start = 8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(
                body,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun SubmittedContent(
    state: ScreenshotHelpUiState.Submitted,
    onPickScreenshot: () -> Unit,
    onRefreshStatus: () -> Unit,
) {
    Text(
        text = "求助已送达",
        modifier = Modifier.semantics { heading() },
        color = MaterialTheme.colorScheme.primary,
        style = MaterialTheme.typography.headlineMedium,
    )
    InfoCard(
        title = "服务端处理记录",
        body = "服务端已校验脱敏副本并立即丢弃图片。服务端还没有连接 OCR、视觉模型或 Agent，因此暂时不会返回自动答案。",
    )
    InfoCard(
        title = "处理分支",
        body = when (state.intent) {
            HelpRequestIntent.RECORDED_TUTORIAL -> "将尝试匹配已录制教程。"
            HelpRequestIntent.GENERAL_GUIDANCE -> "将准备无录制教程时的基础指引。"
        },
    )
    InfoCard(
        title = "当前处理状态",
        body = processingStatusLabel(state.processingStatus),
    )
    state.humanReviewReason?.let { reason ->
        InfoCard(
            title = "需要人工复核的原因",
            body = reason,
        )
    }
    state.guidance?.let { guidance ->
        Text(
            text = guidance.title,
            modifier = Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
        )
        guidance.steps.forEachIndexed { index, step ->
            InfoCard(
                title = "第 ${index + 1} 步：${step.title}",
                body = "${step.instruction}\n\n请你亲自完成这一步，老牌子不会代替点击。",
            )
        }
    }
    InfoCard(
        title = "请求编号",
        body = state.serverReceipt.requestId,
    )
    if (state.statusError == ScreenshotHelpError.StatusFetchFailed) {
        ErrorCard("处理状态暂时无法读取，请稍后重试。")
    }
    OutlinedButton(
        onClick = onRefreshStatus,
        enabled = !state.isRefreshingStatus,
        modifier = Modifier
            .fillMaxWidth()
            .height(56.dp),
    ) {
        Text(if (state.isRefreshingStatus) "正在刷新处理状态……" else "刷新处理状态")
    }
    Button(
        onClick = onPickScreenshot,
        modifier = Modifier
            .fillMaxWidth()
            .height(60.dp),
    ) {
        Text("再问一个问题")
    }
}

private fun processingStatusLabel(status: HelpRequestProcessingStatus): String = when (status) {
    HelpRequestProcessingStatus.RECEIVED -> "已接收，正在等待处理。"
    HelpRequestProcessingStatus.PROCESSING -> "正在处理，暂时不会自动操作手机。"
    HelpRequestProcessingStatus.NEEDS_HUMAN_REVIEW -> "需要人工复核，已暂停自动生成指引。"
    HelpRequestProcessingStatus.GUIDANCE_READY -> "基础指引已生成，请逐步阅读并亲自操作。"
}

@Composable
private fun ScreenshotPreview(
    screenshot: InMemoryScreenshot,
    redactions: List<NormalizedRedaction> = emptyList(),
    suggestions: List<OcrPrivacySuggestion> = emptyList(),
    contentDescription: String = "已脱敏截图",
    onAddRedaction: ((NormalizedRedaction) -> Unit)? = null,
) {
    val bitmap = remember(screenshot) {
        BitmapFactory.decodeByteArray(
            screenshot.encodedBytes,
            0,
            screenshot.encodedBytes.size,
        )
    }
    DisposableEffect(bitmap) {
        onDispose { bitmap?.recycle() }
    }
    if (bitmap == null) {
        ErrorCard("图片预览暂时不可用。")
        return
    }
    val borderColor = MaterialTheme.colorScheme.primary
    var dragStart by remember(screenshot) { mutableStateOf<Offset?>(null) }
    var dragEnd by remember(screenshot) { mutableStateOf<Offset?>(null) }
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(screenshot.width.toFloat() / screenshot.height)
            .background(Color.Black, RoundedCornerShape(16.dp)),
    ) {
        Image(
            bitmap = bitmap.asImageBitmap(),
            contentDescription = contentDescription,
            modifier = Modifier.fillMaxSize(),
        )
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .then(
                    if (onAddRedaction == null) {
                        Modifier
                    } else {
                        Modifier.pointerInput(screenshot) {
                            detectDragGestures(
                                onDragStart = { offset ->
                                    dragStart = offset
                                    dragEnd = offset
                                },
                                onDrag = { change, _ ->
                                    change.consume()
                                    dragEnd = change.position
                                },
                                onDragCancel = {
                                    dragStart = null
                                    dragEnd = null
                                },
                                onDragEnd = {
                                    val start = dragStart
                                    val end = dragEnd
                                    if (start != null && end != null &&
                                        size.width > 0 && size.height > 0
                                    ) {
                                        NormalizedRedaction.fromDrag(
                                            startX = start.x / size.width,
                                            startY = start.y / size.height,
                                            endX = end.x / size.width,
                                            endY = end.y / size.height,
                                        )?.let(onAddRedaction)
                                    }
                                    dragStart = null
                                    dragEnd = null
                                },
                            )
                        }
                    },
                ),
        ) {
            redactions.forEach { redaction ->
                drawRedaction(redaction, borderColor)
            }
            suggestions.forEach { suggestion ->
                drawSuggestion(suggestion.bounds)
            }
            val start = dragStart
            val end = dragEnd
            if (start != null && end != null) {
                NormalizedRedaction.fromDrag(
                    startX = start.x / size.width,
                    startY = start.y / size.height,
                    endX = end.x / size.width,
                    endY = end.y / size.height,
                    minimumDimension = 0f,
                )?.let { drawRedaction(it, borderColor) }
            }
        }
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawRedaction(
    redaction: NormalizedRedaction,
    borderColor: Color,
) {
    val topLeft = Offset(redaction.left * size.width, redaction.top * size.height)
    val maskSize = Size(
        (redaction.right - redaction.left) * size.width,
        (redaction.bottom - redaction.top) * size.height,
    )
    drawRect(Color.Black.copy(alpha = 0.82f), topLeft = topLeft, size = maskSize)
    drawRect(
        color = borderColor,
        topLeft = topLeft,
        size = maskSize,
        style = androidx.compose.ui.graphics.drawscope.Stroke(width = 4.dp.toPx()),
    )
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawSuggestion(
    suggestion: NormalizedRedaction,
) {
    val topLeft = Offset(suggestion.left * size.width, suggestion.top * size.height)
    val suggestionSize = Size(
        (suggestion.right - suggestion.left) * size.width,
        (suggestion.bottom - suggestion.top) * size.height,
    )
    drawRect(
        color = Color(0xFFFFA000),
        topLeft = topLeft,
        size = suggestionSize,
        style = androidx.compose.ui.graphics.drawscope.Stroke(width = 5.dp.toPx()),
    )
}

@Composable
private fun BusyContent(message: String) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        CircularProgressIndicator(modifier = Modifier.size(52.dp), strokeWidth = 5.dp)
        Text(message, style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun InfoCard(title: String, body: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainer,
        ),
        shape = RoundedCornerShape(18.dp),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            Text(
                body,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
    }
}

@Composable
private fun ErrorCard(message: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        ),
    ) {
        Text(
            text = message,
            modifier = Modifier.padding(18.dp),
            color = MaterialTheme.colorScheme.onErrorContainer,
            style = MaterialTheme.typography.bodyLarge,
        )
    }
}
