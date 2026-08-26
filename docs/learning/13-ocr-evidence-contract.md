# 模块 13：OCR 能力边界与可替换证据合同

## 1. 本模块的目标

模块 12 已经可以把用户确认过的脱敏截图发送到受限接口，但还没有识别截图内容。本模块先不安装 OCR SDK，也不调用模型，而是把 OCR 放进一个可替换、可审计的证据边界：

```text
OCR provider 的临时文字块
  → OcrObservationBuilder
  → 只保留 anchor_id、置信度和归一化边界
  → ScreenMatcher 做确定性匹配
```

这样可以先验证安全规则和状态流，再选择 Android 本地 OCR、后端 OCR worker 或多模态视觉服务。

## 2. 为什么不先安装 OCR SDK

OCR 供应商会影响包体、中文模型下载、离线能力、隐私边界和测试方式。若现在直接把某个 SDK 写进 ViewModel，后续更换方案会把 UI、网络和执行器一起改动。

当前实现只定义 Kotlin 端口使用的值对象：

- `OcrStrategy`：`OnDevice`、`BackendWorker`、`VisionModel`；
- `OcrInputKind`：`LocalSession` 或 `SanitizedScreenshot`；
- `OcrTextBlock`：只在一次识别会话内存在的原文块；
- `OcrObservationBuilder`：把原文块消费成不含原文的锚点证据。

这和 Java 后端把 Controller DTO 映射为不可变 Command 很像：SDK 是 adapter，业务规则不应该依赖它的返回类型。

## 3. 三种策略的安全矩阵

| 策略 | 本地会话 | 脱敏副本 | 当前结论 |
| --- | --- | --- | --- |
| Android 本地 OCR | 允许 | 允许 | 第一候选，隐私和离线能力最好 |
| 后端 OCR worker | 禁止 | 仅在 `network_allowed` 下允许 | 适合统一升级，但需要服务端数据边界 |
| 多模态视觉服务 | 禁止 | 仅在 `network_allowed` 下允许 | 理解能力强，但成本、延迟和输出验证复杂 |

“网络允许”不等于“原图可以上传”。`BackendWorker` 和 `VisionModel` 还必须收到 `SanitizedScreenshot`。`capture_paused` 永远不会生成 OCR 观察结果。

## 4. 为什么 OCR 结果不能直接成为安全决定

OCR 可能漏字、错字、把按钮和背景混在一起。`OcrObservationBuilder` 只使用教程锚点中明确声明的 `ocr_text`：

- 不会把 Accessibility 的 `text` 或 `contentDescription` 偷换成 OCR 证据；
- 只做规范化后的精确匹配或最小子串匹配；
- provider 置信度会进入结果，低于 `0.80` 的证据不会提供可用边界；
- forbidden anchor 仍会交给既有 `ScreenMatcher`，出现时保持 `Mismatch`；
- OCR 结果本身不能绕过金融、不可逆动作和页面结果验证策略。

输出的 `ScreenObservation` 只保留：

```text
anchor_id + confidence + normalized_bounds
evidence_source = Ocr
ocr_strategy + ocr_input_kind
```

原始文字不会从 builder 返回。调用方应在构建观察结果后立即丢弃 provider 结果；真实 OCR adapter 还需要清理图片和临时缓冲。

## 5. 与现有 Accessibility 观察的关系

Accessibility 和 OCR 是两种不同的证据来源：

- Accessibility 更适合 resource id、可访问性描述和结构关系；
- OCR 更适合自绘页面、图片按钮和 Accessibility 没有暴露文本的界面。

本模块没有静默合并两种来源。`ScreenObservation.evidenceSource` 明确记录来源，后续如果需要融合，应定义独立的证据合并规则和冲突测试，而不是让一个来源覆盖另一个来源。

## 6. 测试学到的边界

Android JVM 测试覆盖：

- 本地 OCR 能匹配 `ocr_text` 并保留归一化边界；
- 缺少 `ocr_text` 时不会退回 Accessibility 文本；
- 后端/视觉策略不能读取本地会话，也不能在 `local_only` 下运行；
- `capture_paused` 和包名不一致时拒绝生成证据；
- 观察结果标记为 OCR 来源及其输入类型。

这里的测试不要求真实 OCR 引擎，因此不需要网络、付费模型或图片样本，运行速度和可重复性都更接近纯 Java 单元测试。

## 7. 下一步如何选型

下一模块再做真实 provider 的小型基准：使用经过许可的中文 UI 样本，比较识别准确率、耗时、包体、首次模型下载、脱网行为和隐私日志。接入前会单独说明需要新增的 Gradle 依赖及其下载影响。

无论最终选择哪种 provider，它都只能生成建议证据或基础解释输入。真正的教程推进仍由页面匹配、风险策略和用户亲自操作共同决定。
