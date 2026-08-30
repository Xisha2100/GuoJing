# 模块 24：LangGraph-compatible 求助编排骨架

## 为什么先做“兼容骨架”

LangGraph/Deep Agents 适合把多个 Agent 节点连接成有状态流程，但它们不应拥有领域状态的最终写权限。先用普通 Python 定义同样的节点边界，可以在没有模型、网络和付费服务的情况下验证状态机，后续再把这些函数注册到 LangGraph 节点，不改变安全规则。

## 工作流节点

```text
读取 received 结果
  ├─ general_guidance -> 确定性基础指引处理器 -> completed
  └─ tutorial_match  -> mark_processing
          ├─ 没有证据 -> awaiting_evidence（保持 processing，可补证据后重试）
          ├─ 证据不确定/版本需复核 -> needs_human_review
  └─ 强匹配 -> tutorial_matched（持久化并等待人工确认说明）
```

`HelpRequestWorkflowState` 只保存请求结果、阶段和匹配决策，不保存截图、OCR 原文或 Accessibility 节点树。工作流节点不能点击第三方 APP，也不能直接把 UI 回调当作状态迁移。模块 27 将阶段和安全的教程候选摘要写入结果 Repository，让 API 可以在重启后轮询。

## 可恢复性

教程分支在缺少证据时只推进到 `processing`，并返回 `awaiting_evidence`。客户端或本地观察器上传一个新的受控 Envelope 后可以再次运行；第二次运行会识别当前已经是 `processing`，不会重复调用 `mark_processing`。模块 27 进一步保存 `workflow_stage`、匹配状态、graph/node/revision 元数据；这才是可跨进程读取的最小 checkpoint，未来可以映射为 LangGraph 的持久化状态。

## 为什么通用指引与教程分支不同

通用指引来自已审核的静态目录，可以在一次处理中直接进入 `guidance_ready`。教程分支需要页面匹配和版本兼容评估；即使匹配成功，也只返回 `tutorial_matched` 并进入人工复核，后续模型只能生成需要用户亲自完成的说明，不能生成 Android 节点动作。

## Java/Python 对照

| Python | Java/Kotlin 对照 |
| --- | --- |
| `HelpRequestWorkflowState` | immutable state record |
| `HelpRequestWorkflowStage` | sealed state / enum |
| 注入的 service/processor | constructor injection |
| `run()` | application use case / orchestrator |
| 未来 LangGraph node | state transition handler |

## 当前边界

本模块没有把 `langgraph` 或 `deepagents` 加入生产依赖，因此测试不需要模型 API Key，也不会因为第三方 SDK 版本变化而改变行为。模块 25 定义模型适配器和结构化输出校验；模块 27 先把确定性工作流接到生产入口，只有通过后续安全边界的模型结果，才可以作为人工说明候选进入既有状态机。
