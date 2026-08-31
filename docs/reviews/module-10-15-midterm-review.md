# 模块 10–15 中期代码检查报告

检查日期：2026-08-30

检查范围：模块 10–15 的规划与学习文档、Android Accessibility Overlay、截图导入与像素脱敏、显式求助上传、OCR 证据合同、ML Kit provider、OCR 隐私建议，以及对应 Python/Android 测试。

## 结论

模块 10–15 的总体架构方向正确：浮层不可触摸且不执行节点动作；截图通过系统选择器进入会话内存并生成真实像素遮挡副本；发送需要独立同意；OCR provider、证据构建和 UI 状态之间有明确端口；OCR 原文没有进入 Compose 状态。

但当前存在 3 个高严重度问题和 3 个中严重度问题。其中最严重的是模块 12 的校验失败响应会原样回显完整截图 Base64，并且缺少 `no-store` 缓存头；此外，浮层会在证据丢失或 Service 重连时显示旧页面指引，开放上传接口也没有在 JSON 解析前限制请求体。建议在修复 P1 问题前，不把模块 10–15 视为可进入真实用户试用的隐私安全闭环。

## 模块符合度

| 模块 | 结论 | 主要原因 |
| --- | --- | --- |
| 10：跨 APP 引导与结果验证 | 部分符合 | 不触摸、目标包校验和双 target 匹配已实现，但浮层在证据丢失/重连时可能恢复旧指引；版本兼容状态没有进入 Android 决策。 |
| 11：截图求助与本地脱敏 | 基本符合 | Photo Picker、尺寸上界、会话清理和真实像素遮挡符合规划；ViewModel 仍可构造互斥的隐私元数据状态。 |
| 12：求助请求与显式发送 | 不符合安全收口要求 | 校验失败会回显完整 Base64，开放接口也没有传输层请求体上限。 |
| 13：OCR 证据合同 | 部分符合 | 策略矩阵和无原文输出正确，但子串匹配可以让同一短文本同时满足多个锚点。 |
| 14：ML Kit 本地 OCR | 符合当前规划 | 打包模型、本地执行、可取消桥接及临时 Bitmap 生命周期与文档一致。 |
| 15：OCR 隐私建议 | 基本符合 | 原文未进入 UI 状态，Pending/截断均阻止继续；应用层仍缺少互斥状态的最终防线。 |

## 严重问题

### P1-1：请求校验失败时，422 响应会回显完整截图 Base64 且允许默认缓存

证据：

- `src/guojing/application/help_requests/dto.py:45-53` 使用 Pydantic model validator 校验遮挡数与“无隐私确认”的互斥关系。
- 应用没有注册 `RequestValidationError` 的脱敏异常处理器。FastAPI 默认错误结构会把 validator 收到的整个 `input` 放入响应。
- `src/guojing/api/help_requests.py:141-159` 中的 `Cache-Control: no-store` 只在路由函数已经开始执行后设置；请求体模型校验失败发生在此之前。

最小复现：提交一份 `redaction_count=1` 且 `no_sensitive_content_confirmed=true` 的请求，返回：

```text
status = 422
base64_echoed = true
cache-control = null
pragma = null
```

响应的 `detail[0].input.sanitized_image_base64` 包含完整上传图片，而不是摘要或占位符。

影响：这直接违反模块 12 “响应不回显图片内容”的承诺。即使图片被用户认为已脱敏，它仍可能包含漏选的聊天、余额或身份信息；错误响应还可能进入客户端日志、反向代理、APM、抓包记录或缓存。正常 202 路径的“不回显”测试不能覆盖此问题。

建议：

- 为 `RequestValidationError` 注册全局或路由级安全处理器，删除 `input`、`ctx.error` 和任何请求值，只返回字段位置、稳定错误码和脱敏消息。
- 让包括 4xx/5xx 在内的所有求助接口响应统一携带 `Cache-Control: no-store` 和 `Pragma: no-cache`，不要依赖路由函数内赋值。
- 增加 model-level、field-level、未知字段、超长 Base64 和格式错误的回归测试，断言响应体、响应头及日志中均不存在 Base64、问题正文和 SHA 以外的图片内容。

### P1-2：Accessibility 浮层在页面证据丢失或 Service 重连时可能显示旧指引

证据：

- `android/app/src/main/java/com/xisha/guojing/observation/GuoJingAccessibilityService.kt:36-39` 在目标包事件的 `rootInActiveWindow == null` 时直接返回，没有隐藏已有浮层。
- `android/app/src/main/java/com/xisha/guojing/observation/GuoJingAccessibilityService.kt:63-79` 在 Service 连接/重连后恢复全局 `Visible` 命令时，只比较当前根节点包名，不重新验证 source node 的强匹配证据。
- `AccessibilityGuidanceCoordinator` 是进程级单例；Service 重建时旧 `Visible` 状态仍可能存在。

影响：同一个 APP 内页面已经切换、窗口处于过渡态或 Service 被系统重建时，只要包名相同，旧步骤卡、箭头和框选就可能覆盖到错误控件上。浮层虽然不接收触摸，但会诱导用户亲自点击其后方的错误位置，违反模块 10 “证据变弱立即隐藏”和“只有 source node 强匹配才显示”的核心安全边界。

建议：

- 任何无法取得实时 root、构建观察失败、隐私暂停或证据未知的路径都应 fail closed，立即 `temporarilyHide()`。
- Service 重连不能仅凭包名恢复可见浮层；应先保持隐藏，等待属于当前 observation request 的新 `Available` 序列经 ViewModel 强匹配后重新 `show()`。
- 给 Overlay 命令加入 observation request/session ID 和匹配序列，Service 显示前验证命令仍属于当前请求。
- 增加 Service/Robolectric 或设备回归测试：root 为空、同包换页、Service 重建、capture paused 和弱匹配都必须保持隐藏。

### P1-3：开放的 Base64 上传接口没有在解析前限制 HTTP 请求体，可被低成本内存拒绝服务

证据：

- `src/guojing/application/help_requests/dto.py:16,43` 的 Base64 长度上限只在 FastAPI/Starlette 已经读取并解析 JSON 后由 Pydantic 执行。
- `src/guojing/main.py` 没有请求体限制 middleware；仓库也没有反向代理或 ASGI server 的 body-size 配置。
- 模块 12 明确记录当前接口没有登录、设备身份、速率限制或配额。

影响：攻击者不需要通过字段校验即可发送远大于 8 MiB 的 JSON 或 chunked body。服务器会先为原始请求体、JSON 字符串和解析对象分配内存，再返回 422；并发请求可以耗尽 worker 内存。当前“图片最多 8 MiB”是业务字段上限，不是实际传输/资源上限。

建议：在可信反向代理和 ASGI 入口同时设置略高于合法 JSON Base64 的硬上限；对缺失/伪造 `Content-Length` 的流式请求也必须在读取过程中停止。再增加设备/会话认证、并发限制和速率限制。测试应直接发送超限原始 body，确认应用在完整缓冲前返回 413。

## 中严重度问题

### P2-1：Android 读取了 APP 版本，却完全没有执行版本兼容性决策

证据：

- `GuoJingAccessibilityService.readObservedApp()` 读取 `versionName/versionCode`。
- `TutorialDetailJsonParser` 解析 `recordedApp.versionCode` 和节点 `lastVerifiedVersionCode`。
- `android/app/src/main/java/com/xisha/guojing/observation/ScreenMatcher.kt:32-39` 只检查包名；Android 主代码中没有其他位置使用 observed version 或 `lastVerifiedVersionCode`。

影响：目标 APP 更新后，Android 仍可能凭通用文字/资源 ID 把页面判为强匹配并显示引导。高风险 transition 仍由执行引擎阻止，因此当前不等同于直接金融越权；但它没有实现学习文档所称的 recorded-app compatibility，也无法把新版低风险试运行标成 provisional 或要求对应 target 证据完成兼容确认。

建议：把后端 `assess_node_reuse()` 的兼容语义移植为共享测试向量下的 Kotlin 策略。source 匹配、浮层显示、target 验证和完成状态都应携带 same-version/provisional/stale 决策，不应只显示录制版本文字。

### P2-2：OCR 子串匹配可让同一个两字文本同时满足多个锚点

证据：

- `android/app/src/main/java/com/xisha/guojing/observation/OcrEvidence.kt:109-117` 在 expected 长度至少 2 时，允许 `expected.contains(actual)`，但没有约束 actual 的最小长度或覆盖比例。
- `bestEvidence()` 为每个 anchor 独立扫描同一 blocks 列表，没有一对一分配；同一个 OCR block 可以重复成为多个锚点的最佳证据。

例如 OCR 只识别到“微信”时，它可以同时对子串包含“微信”的 required 和 optional 锚点给出 `0.90`。一个 required、一个 optional 且结构分为 1.0 时，总分可达到：

```text
0.90 × 0.75 + 0.90 × 0.10 + 1.00 × 0.15 = 0.915
```

超过 `matched=0.90` 门槛。

影响：当前 `OcrObservationBuilder` 尚未接入教程 ViewModel，因此这是接入前的设计阻断项，而不是已上线路径；一旦接入，通用短词可能在错误页面制造强匹配、错误边界和浮层指引。

建议：要求实际文本达到独立最小长度和覆盖率；避免对 `expected.contains(actual)` 给予接近精确匹配的置信度；同一 block 默认不能同时满足多个 required/optional 锚点；加入相对位置与一对一匹配测试。

### P2-3：ViewModel 可构造“已有遮挡但同时确认无隐私”的互斥状态

证据：

- `ScreenshotHelpViewModel.addRedaction()` 和 `acceptPrivacySuggestion()` 会把 `noSensitiveContentConfirmed` 重置为 false。
- 但 `android/app/src/main/java/com/xisha/guojing/ui/help/ScreenshotHelpViewModel.kt:164-173` 的 `setNoSensitiveContentConfirmed(true)` 只检查 Pending 建议，没有检查 `redactions.isEmpty()`。
- `ScreenshotHelpUiState.Editing.canSanitize` 对这一互斥组合仍返回 true，随后 receipt 会同时包含 `redactionCount > 0` 与 `noSensitiveContentConfirmed=true`。

影响：Compose 通常会在有遮挡后隐藏该复选框，但应用层不变量仍可被滞后的 UI 回调、测试或未来入口绕过。脱敏副本会进入 Ready，最终由后端 422 拒绝；用户无法在 Ready 中修复元数据，只能重选截图。

建议：在 ViewModel 和 `ScreenshotSanitizationReceipt` 两层拒绝互斥组合；`canSanitize` 也应显式检查。增加“先加遮挡、再调用无隐私确认”以及反向顺序的回归测试。

## 已验证项目

- `uv run pytest -q`：122 passed。
- Android JVM：84 tests，0 failures。
- `cd android && ./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest`：BUILD SUCCESSFUL。
- `uv run ruff check .`：通过。
- `uv run mypy`：通过（98 个源文件）。
- `uv lock --check`：通过。
- `git diff --check`：通过。

`uv run ruff format --check .` 当前未通过，原因是审查范围之外、并在审查期间继续变化的模块 21 文件 `migrations/versions/20260830_04_create_help_request_results.py` 和 `src/guojing/application/help_requests/evidence_dto.py` 需要格式化；本次审查没有修改这两个文件，也没有把它们计入模块 10–15 结论。

现有自动化全部覆盖了主要成功路径，但没有覆盖校验错误的隐私响应、ASGI 请求体上限、Service 重连/无 root 浮层隐藏、版本漂移、跨锚点 OCR block 复用和互斥隐私状态。这些路径应作为修复后的新增回归门槛。
