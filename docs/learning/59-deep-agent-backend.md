# 59：Deep Agent 视觉指引后端

## 为什么重构

旧系统的中心是人工维护和发布教程图，后端再用固定动作目录匹配求助。这与“根据用户当前界面，由多模态模型现场给出下一步”并不是同一个产品。本模块删除旧教程、草稿、管理员、人工审核和伪 Agent 业务链，把第一阶段收敛为一个可以独立运行的视觉指引后端。

Android 暂时保留但没有接入新协议，避免在 Agent 行为尚未稳定时同时调试客户端。它不是本阶段验收门槛。

## 一轮请求如何流动

1. 客户端创建 24 小时会话，保存只返回一次的会话令牌。
2. 客户端提交目标、包名、截图和幂等回合 ID。
3. API 校验 Base64、文件签名、媒体类型、实际尺寸、8 MiB 与 4096 像素限制，只把 SHA-256 和安全元数据写入数据库。
4. 有界内存队列保管可清零的截图字节；Worker 为会话取得隔离 Docker 沙箱。
5. 主 Agent 同时把截图作为多模态 `image_url` 发送给模型，并写入沙箱 `/workspace/current-screen.jpg` 供内置工具使用。
6. 主 Agent 必须依次调用 `ui-analyst` 和 `guidance-reviewer`。前者继承截图上下文，后者隔离运行，只接收分析文本与候选步骤。
7. `ToolStrategy(GuidanceDecisionOutput)` 验证唯一的最终步骤；低置信度结果变为 `cannot_determine`。
8. API 只通过 GET/SSE 暴露 run 状态和最终结构，不暴露工具、子智能体对话或推理。
9. Worker 尽力覆盖内存并删除沙箱截图；关闭会话或空闲超时会销毁整个容器。

## 领域约束

`GuidanceDecision` 只有三种状态：

- `continue`：必须有一条不超过 300 字的说明、合法归一化矩形和达到阈值的置信度。
- `completed`：没有目标矩形。
- `cannot_determine`：没有目标矩形，客户端可以保持页面稳定后重试。

坐标必须位于 `0…1`，且 `left < right`、`top < bottom`。返回值是给用户看的说明，不是可执行的 Android 动作。首版不判断支付、删除、授权和验证码风险，因此产品端不能将结果用于自动操作。

## Deep Agents 组合

生产代码直接导入并调用 `deepagents.create_deep_agent()`，不是项目内的同名抽象。模型是指向 DeepSeek OpenAI 兼容地址的 `ChatOpenAI`，关闭 SDK 自动重试，由 run 层统一产生可重试失败。

子智能体的工具列表为空，不能继续委派；主 Agent 的调用轨迹会在内存中验证为严格的 `ui-analyst → guidance-reviewer`。整个调用不设置 LangGraph checkpointer，每轮根据数据库中的最终文字步骤重建上下文。调用范围还显式关闭 LangSmith tracing，避免部署环境中的全局 tracing 配置上传截图或消息。

截图、用户目标和历史说明都应当视为不可信数据。系统提示禁止服从界面中的“忽略规则”“读取密钥”“执行命令”等文本。即使模型误用工具，副作用仍被 Docker 边界限制。

## Docker 安全边界

每个会话最多一个容器，配置包括：

- 无网络，且不挂载宿主机目录或 Docker socket；
- 只读根文件系统，只有 `/workspace` 与 `/tmp` 是临时可写目录；
- 非 root 数字用户、移除全部 capabilities、`no-new-privileges`；
- 0.5 CPU、512 MiB、64 PIDs；
- 单命令最多 10 秒、返回最多 16 KiB；
- 空闲 10 分钟清理，服务启动清理带专用 label 的遗留容器。

主服务必须能够访问 Docker Engine，因此生产上应使用独立内网 Worker、最小化 Engine ACL，并禁止把 Docker API 暴露到公网。沙箱容器不会得到 DeepSeek、数据库或云服务环境变量。

## 持久化与恢复

最终结构只有三张业务表：

- `agent_sessions`：令牌摘要、目标、包名、状态、步骤和过期时间；
- `agent_runs`：幂等 ID、图片摘要、状态、最终结果、错误码、模型名和耗时；
- `guidance_steps`：用于下一轮上下文的最终文字步骤和坐标。

未完成 run 在进程重启后转为 `failed/server_restarted`，客户端用原 `client_turn_id` 和相同截图重试。失败不切换其他模型。旧迁移保留以支持已有数据库升级，新迁移删除遗留业务表；这是有意不可逆的数据迁移。

## 测试策略

默认单元和 API 测试使用 Fake Agent/Fake Sandbox，检查结构约束、多模态消息、固定子智能体、令牌隔离、图片边界、SSE、重启恢复和数据库结构。Docker 参数通过假 Engine 验证，不依赖本机 Docker。

真实 DeepSeek 与真实 Docker 属于显式集成验收，需要部署方提供临时密钥、预拉取镜像和测试截图。任何测试日志都不得打印 Base64、截图内容、完整模型消息或 Shell 原始输出。
