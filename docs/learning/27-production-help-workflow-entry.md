# 模块 27：生产求助工作流入口与可轮询检查点

## 1. 本模块解决的问题

模块 21–25 已经分别实现了结果持久化、受控证据、教程匹配、编排骨架和模型输出校验，但这些组件之前主要通过单元测试连接。生产 API 仍然只会调用基础指引处理器，录制教程求助不会真正读取证据并匹配教程。

本模块把这些组件接到一个明确的 composition root，并为管理员提供一个受认证的运行入口：

```text
POST /api/v1/help-requests
        │
        ├─ recorded_tutorial ── 上传受控 EvidenceEnvelope
        │                         │
        │                         └─ 管理员 process
        │                              ├─ awaiting_evidence
        │                              ├─ tutorial_matched
        │                              └─ needs_human_review
        │
        └─ general_guidance ─── 管理员 process -> completed

GET /api/v1/help-requests/{request_id}
        └─ 读取持久化 workflow_stage 和安全 tutorial_match 摘要
```

工作流仍然不会点击第三方 APP，也不会把截图、OCR 原文或 Accessibility 节点树存入结果表。

## 2. Composition Root：为什么装配必须发生在 `main.py`

`HelpRequestWorkflow` 依赖四个能力：

| 依赖 | 生产实现 | 责任 |
| --- | --- | --- |
| `HelpRequestService` | SQLite Repository-backed service | 状态迁移与结果 TTL |
| `HelpRequestEvidenceService` | SQLite evidence Repository-backed service | 校验和读取受控页面证据 |
| `TutorialMatchService` | `TutorialService` 的适配器 | 选择当前包名的已发布教程节点 |
| `DeterministicHelpRequestProcessor` | 无模型基础指引处理器 | 未接入模型时提供安全的静态指引 |

`create_app()` 现在创建并保存一个 `HelpRequestWorkflow` 到 `application.state`。HTTP 层通过 `get_help_request_workflow()` 获取它，而不是在路由函数中临时 `new` 一个处理器。

这和 Java/Spring 的关系很直接：

- `main.py` 类似 `@Configuration` 或 `@Bean` 装配处；
- `HelpRequestWorkflow` 类似 application service；
- `TutorialMatchService` 和 Repository 是 constructor injection 的端口实现；
- FastAPI `Depends` 类似把已装配的 bean 传给 controller。

如果把对象创建散落到 controller，单元测试很容易通过，但生产请求会绕过真正的 matcher 或使用另一份内存状态。

## 3. 可持久化的工作流检查点

`HelpRequestWorkflowState` 是一次调用返回的不可变状态；这次增加的字段则写入 `help_request_results`：

- `workflow_stage`：`received`、`awaiting_evidence`、`tutorial_matched`、`needs_human_review` 或 `completed`；
- `tutorial_match_status` 与 `tutorial_match_reason`：机器可读的决定；
- `tutorial_graph_id`、`tutorial_node_id`、`tutorial_revision_number`：候选教程的安全标识。

这些列故意不包含：

- 问题原文；
- OCR 文本或 Accessibility 节点树；
- 截图字节；
- 可执行坐标、手势或支付命令。

强匹配的结果状态仍是 `needs_human_review`。`tutorial_matched` 是更具体的工作流阶段，而不是“可以自动执行”的授权。人工确认版本和说明后，管理员发布的手动指引会进入 `completed`。

新增 Alembic revision `20260830_06` 使用可空列，因此旧结果可以平滑升级；Repository 在读取时会把六列重新组装为不可变的 `HelpRequestTutorialMatch`。

## 4. 为什么 `GET` 只读检查点，不能顺便再次运行工作流

状态轮询必须是幂等的读取。若每次 `GET` 都重新匹配：

1. 教程重新发布后，旧请求可能得到不同 revision；
2. 证据过期后，原本的决定可能漂移；
3. 一个看似读取的请求会触发状态迁移或重复处理。

因此 `HelpRequestWorkflow.inspect()` 只把已保存的 `HelpRequestResult` 映射为状态视图，不调用 matcher、不写数据库。只有管理员的 `POST .../process` 才执行一次有边界的 workflow pass。

## 5. API 示例

管理员提交处理请求后，教程强匹配会返回：

```json
{
  "processing_status": "needs_human_review",
  "workflow_stage": "tutorial_matched",
  "tutorial_match": {
    "status": "matched",
    "reason": "strong_match",
    "graph_id": "wechat_open_family_chat",
    "node_id": "chat_list",
    "revision_number": 1
  },
  "human_review_reason": "教程页面已匹配,请人工确认版本和步骤后发布安全说明。"
}
```

随后客户端轮询同一个 status endpoint，会得到相同的阶段和候选摘要。测试还创建了第二个应用实例读取同一 SQLite 数据库，验证该状态不是某个 Python 进程里的临时对象。

Android 的 `HttpHelpRequestStatusReader` 增加了对应的 `HelpRequestWorkflowStage` 和 `HelpRequestTutorialMatch`，并对未知阶段、候选字段不完整以及阶段/处理状态矛盾的响应 fail-closed。界面只显示教程图、节点和修订号，不显示任何原始页面文本。

## 6. 为什么仍然不直接接 Deep Agent

本模块解决的是“真实请求能走到哪一个安全节点”，不是模型选型。`main.py` 仍注入确定性的基础处理器，原因是：

- 没有 API Key 或网络时也能运行完整回归；
- matcher 和人工复核边界先稳定；
- 模型输出仍必须经过模块 25 的结构化解析和领域安全检查；
- 一个模型超时不能阻塞 HTTP 线程，也不能绕过教程版本与风险规则。

未来替换 `DeterministicHelpRequestProcessor` 时，入口保持不变，只替换实现并增加超时、lease、模型相关上下文和可审计的候选引用。

## 7. 验证与学习要点

本模块新增和更新的验证包括：

- API：发布教程 → 提交截图求助 → 上传语义证据 → 管理员运行工作流 → 新应用实例轮询；
- SQLite：教程匹配检查点跨 Repository 实例 round-trip；
- Python：155 个测试、Ruff、格式检查和严格 mypy；
- Android：状态解析的强匹配、未知阶段和一致性校验，JVM 单元测试通过。

对有 Java 后端经验的开发者，最值得记住的是：**状态机的内存对象不是持久化检查点**。只有把最小、脱敏、可版本化的状态写入 Repository，并让读取端只投影这份状态，服务重启和多 worker 才不会改变客户端看到的事实。

## 8. 当前限制与下一步

本模块没有声称解决中期 review 的全部生产问题，仍需后续单独处理：

- evidence 的服务端时间窗口、最大 TTL、请求归属与单请求容量；
- SQL Repository 的 compare-and-swap，避免旧 worker 覆盖新终态；
- 模型上下文的最小任务相关语义与真实超时/lease；
- 基于允许的 transition/risk ID，而不是自由文本黑名单的危险操作防线；
- Android 端真正发送 `EvidenceEnvelope` 的网络用例和用户可见授权。

这些问题分别影响数据一致性、隐私边界或安全授权，不应因为本模块已经能轮询 `tutorial_matched` 就被默认为完成。
