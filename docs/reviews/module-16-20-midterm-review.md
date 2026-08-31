# 模块 16–20 中期代码检查报告

检查日期：2026-08-30

检查范围：模块 16–20 的规划文档、Python 领域层/Application/API、Android 数据与 UI 状态链路、现有 Python/Android 测试。

## 结论

模块 16–20 的主干分层与规划基本一致：结果状态机位于领域层，处理器通过端口接入，截图未进入结果对象，基础目录不含执行命令，人工接口复用了管理员会话与 CSRF。

但当前实现存在 5 个高严重度问题和 1 个中严重度协议问题。它们会导致安全指引绕过、网络重试重复建单、错配响应未能真正 fail closed、处理请求永久卡死，以及发布成功但审计缺失。因此，不能把模块 20 视为已经完成“端到端安全收口”；建议先修复 P1 问题，再进入真实 OCR、教程检索或 Agent 接入。

## 模块符合度

| 模块 | 结论 | 主要原因 |
| --- | --- | --- |
| 16：处理结果契约 | 部分符合 | 后端状态机清晰，但 Android 对所有可见指引字段的安全校验不完整，重复 POST 还可产生非法终态载荷。 |
| 17：处理器端口 | 部分符合 | 端口和确定性分支符合规划，但处理器异常会永久毒化请求。 |
| 18：基础指引目录 | 符合 | 当前固定目录是元数据驱动、人工操作、无坐标/手势的安全模板。 |
| 19：人工复核 | 部分符合 | 会话、CSRF 和领域校验已接入，但危险总标题可绕过，发布与审计不是一致操作。 |
| 20：端到端收口 | 不符合 | Android 实际重试不复用幂等键，响应关联只验证了服务端返回值之间的自洽，没有绑定本地发出的请求。 |

## 严重问题

### P1-1：Android 每次发送都重新生成幂等键，网络重试仍会重复建单

证据：

- `android/app/src/main/java/com/xisha/guojing/data/HelpRequestSender.kt:61-65` 在 `send()` 内部调用 `UUID.randomUUID()`。
- `HelpRequestSubmission` 不保存 `clientRequestId`，`ScreenshotHelpUiState.Ready` 也不保存该值。
- `android/app/src/main/java/com/xisha/guojing/ui/help/ScreenshotHelpViewModel.kt:252-256` 在发送失败后回到原 `Ready`；用户重试时再次进入 `send()`，必然生成新 UUID。

影响：如果第一次 POST 已到达服务端，但响应在客户端超时或断线，第二次点击会使用不同的 `client_request_id`。服务端无法命中模块 20 的幂等映射，会创建第二个请求并可能被处理两次。这与 README 和模块 20 “网络重试复用同一个 `client_request_id`”的声明直接冲突。

建议：在脱敏副本进入 `Ready` 时生成并保存一次 `client_request_id`，让同一 `Ready` 会话的所有发送重试复用它；只有换图、重新脱敏或明确开始新请求时才生成新值。增加“第一次服务端成功但客户端抛网络异常，第二次请求体 ID 不变”的 JVM 测试。

### P1-2：Android 的错配响应校验未绑定本地请求，可能显示其他请求的结果

证据：

- `HttpHelpRequestSender` 生成本地 `clientRequestId` 后，只把它写入请求体；`parseReceipt()` 没有接收期望 ID、意图或路由。
- `android/app/src/main/java/com/xisha/guojing/data/HelpRequestSender.kt:86-103` 直接信任响应中的 `request_id`、`client_request_id`、`processing_route` 和 `status_endpoint`，甚至没有读取响应的 `intent` 进行比对。
- `android/app/src/main/java/com/xisha/guojing/ui/help/ScreenshotHelpViewModel.kt:270-278` 后续只比较状态结果与这个未经验证的服务端收据。该检查能证明“状态响应与收据自洽”，不能证明“收据属于本机刚发送的请求”。

影响：若服务器、代理或并发链路把另一个同意图/同路由请求的收据返回给客户端，客户端会继续查询并展示另一个请求的人工复核原因或指引。模块 20 宣称的客户端 ID、意图和路由 fail-closed 关联并未真正成立。

建议：`send()` 应把本地生成且可重试复用的 `client_request_id`、期望 intent/route 传给收据解析器，严格验证：

- 响应 `client_request_id` 等于本地值；
- 响应 intent 等于提交 intent，route 与 intent 的确定性映射一致；
- `request_id` 是 UUID；
- `status_endpoint` 严格等于该 request ID 的固定相对路径；
- 初次成功响应的状态/载荷组合满足协议。

### P1-3：危险指引可通过总标题绕过双端校验并直接展示

证据：

- `src/guojing/domain/help_requests.py:88-92` 只校验 `HelpRequestGuidance.title` 的非空和长度，没有调用危险词检查。
- 领域层只在 `HelpRequestGuidanceStep.__post_init__()` 中检查步骤标题和正文。
- `android/app/src/main/java/com/xisha/guojing/data/HelpRequestResult.kt:141-157` 对指引总标题和步骤标题只做非空读取，危险词正则只用于 `instruction`。
- `android/app/src/main/java/com/xisha/guojing/ui/help/ScreenshotHelpScreen.kt:567-576` 会突出显示总标题和步骤标题。

最小复现已经确认以下对象能够成功构造：

```python
HelpRequestGuidance(
    title="请点击支付并输入密码",
    steps=(
        HelpRequestGuidanceStep(
            step_id="x",
            title="继续",
            instruction="请按页面提示继续。",
        ),
    ),
)
```

管理员发布接口会接受这份对象，Android 也会显示危险总标题。这直接违反模块 16、19、20 对金融/密码类危险指引的确定性拦截要求。

此外，当前黑名单只覆盖少量精确短语；例如同义词、插入空格或“汇款/确认删除/发送金额”等表达仍可绕过。对于安全边界，仅依赖自然语言黑名单不够稳健。

建议：

- 对指引总标题、步骤标题、步骤正文使用同一个归一化后的安全策略；Android 做同等的纵深校验。
- 人工发布优先选择结构化、已审核的动作类型或模板 ID；未知自由文本默认进入更严格的复核，而不是把黑名单当作完整安全证明。
- 增加每一个可见字段的独立回归测试，并覆盖空格、标点、同义词和大小写变体。

### P1-4：处理器异常会把请求永久卡在 `processing`，无法重试或转人工

证据：

- `src/guojing/application/help_requests/service.py:148-157` 先持久化 `received → processing`，随后在锁外调用 `processor.process()`。
- 对处理器异常没有补偿转换。
- 状态图不允许 `processing → processing`，也没有 `failed/retryable` 状态。

最小复现结果：处理器第一次抛出临时异常后，请求状态为 `processing`；再次调用 `process()` 得到：

```text
ValueError: cannot transition from processing to processing
```

影响：未来接入 OCR、检索、队列或 Agent 后，任何超时、依赖故障或进程内异常都会形成永久悬挂请求。管理员既不能重试，也不能把它转为人工复核；用户会一直看到“正在处理”。这与模块 20 声称覆盖处理失败路径不符。

建议：为领取/执行建立明确的 lease、attempt 和失败策略。最低限度应在异常时原子地转为带安全原因的 `needs_human_review`；生产队列则应支持超时 lease、有限重试和幂等提交终态。增加处理器抛异常、超时和重复投递测试。

### P1-5：人工发布先改变状态、后写审计；审计失败会留下永久未审计的发布

证据：

- `src/guojing/api/help_request_review.py:153-168` 先执行 `service.publish_guidance()`，然后调用 `auth_service.record_action()`。
- `process` 接口同样先推进状态，再在 `src/guojing/api/help_request_review.py:124-130` 写审计。
- 求助结果在内存服务中，审计在数据库中，两次操作没有事务或 outbox。

影响：若数据库写审计时故障，API 会返回 500，但指引已经进入 `guidance_ready`。再次发布会因前向状态机拒绝重复转换而返回 409，缺失的审计也不会被补写。最终形成“用户可见发布已经生效、审计记录不存在”的不可恢复状态，违反模块 19 的审计承诺。

建议：把求助状态和审计落在同一个持久事务中，或使用 transactional outbox。MVP 若仍保留内存状态，至少应让发布操作具备可重放的审计事件 ID，并在审计失败时不向用户暴露未审计终态；增加审计仓库抛异常的回归测试。

## 中严重度协议问题

### P2-1：幂等重试可能返回 `guidance_ready`，但响应中没有 guidance

证据：

- `src/guojing/application/help_requests/service.py:90-102` 对重复请求返回当前 `HelpRequestResult` 转换出的 receipt。
- `src/guojing/application/help_requests/service.py:209-218` 把当前终态复制到 `HelpRequestReceipt.processing_status`，但 receipt 模型没有 guidance 或 review reason。
- `src/guojing/api/help_requests.py:108-125` 因而可构造 `processing_status="guidance_ready"` 且 `guidance=null` 的响应；响应 DTO 没有跨字段校验。

最小复现已得到：

```text
{'processing_status': 'guidance_ready', 'guidance': None, 'human_review_reason': None}
```

影响：这违反 `guidance_ready` 必须带 guidance 的核心状态不变量。Android 收据解析器当前也不会拒绝该组合，UI 会显示“指引已生成”却没有任何步骤，直到用户手动刷新。

建议：重复 POST 要么始终返回最初的 `received` 收据，要么返回完整的当前结果投影；两种选择都必须通过统一的跨字段验证。避免维护一个能表达非法终态的弱化 receipt 模型。

## 已验证项目

- `uv run pytest -q`：118 passed。
- 模块 16–20 后端针对性测试：25 passed。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：98 files already formatted。
- `uv run mypy`：通过（94 个源文件）。
- `uv lock --check`：通过。
- `git diff --check`：通过。
- `cd android && ./gradlew testDebugUnitTest lintDebug`：BUILD SUCCESSFUL。

现有测试全部通过说明常规路径稳定，但上述问题主要位于未覆盖的失败、重试、响应错配和跨存储一致性路径。修复时应优先补回归测试，再修改实现。
