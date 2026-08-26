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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction

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
        body = "本模块还没有连接 OCR、视觉模型或 Agent。原图和脱敏副本都只保存在本次内存会话中。",
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
    if (state.redactions.isEmpty()) {
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
        modifier = Modifier.fillMaxWidth(),
        minLines = 3,
        maxLines = 5,
        label = { Text("例如：下一步应该点哪里？") },
        supportingText = { Text("${state.question.length}/300") },
    )
    if (state.error == ScreenshotHelpError.SanitizationFailed) {
        ErrorCard("脱敏副本生成失败，原图仍只在本次内存会话中，可以重试。")
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

@Composable
private fun ReadyContent(
    state: ScreenshotHelpUiState.Ready,
    onPickScreenshot: () -> Unit,
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
        body = "当前只完成了本地脱敏。OCR、视觉模型和基础指引 Agent 将在后续模块接入。",
    )
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
private fun ScreenshotPreview(
    screenshot: InMemoryScreenshot,
    redactions: List<NormalizedRedaction> = emptyList(),
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
