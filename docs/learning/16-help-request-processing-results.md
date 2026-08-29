# 模块 16：截图求助处理结果契约

## 1. 本模块解决的问题

模块 12 的接口只能告诉客户端“图片校验成功并已丢弃”。如果以后接入教程检索、人工复核或基础指引 Agent，客户端还需要区分：请求刚收到、后台正在处理、因为安全原因暂停，还是已经有一份可阅读的指引。

本模块先把生命周期固定下来，不接入模型和队列：

```text
POST /api/v1/help-requests
  → received
  → GET /api/v1/help-requests/{request_id}
  → processing
  → needs_human_review 或 guidance_ready
```

当前 `POST` 成功后仍停留在 `received`。状态迁移方法已经在 application service 中实现，后续 worker 可以调用它；没有 worker 时不会伪造“正在分析”或“已经回答”。

## 2. 处理状态是受限枚举

后端和 Android 都使用同一组 wire value：

| 状态 | 含义 | 是否允许 guidance |
| --- | --- | --- |
| `received` | 已通过图片和隐私契约校验，图片已丢弃，等待处理 | 否 |
| `processing` | 某个受控 worker 正在处理元数据或候选证据 | 否 |
| `needs_human_review` | 触发安全边界，需要人工复核，自动流程暂停 | 否 |
| `guidance_ready` | 已生成一份可阅读的基础指引 | 是 |

状态只能向前迁移：

```text
received → processing → guidance_ready
                         ↘ needs_human_review → guidance_ready
```

`HelpRequestResult.transition()` 集中保存允许的边，API 和 UI 都不能自行把状态改回去。状态机与 Java 后端中由聚合根保护生命周期不变量的做法相同；Pydantic 只负责 HTTP 结构，不能替代 domain 规则。

## 3. 结果载荷不携带截图

查询接口返回的核心 JSON 如下：

```json
{
  "schema_version": "1.1",
  "request_id": "…",
  "client_request_id": "…",
  "intent": "general_guidance",
  "processing_route": "general_guidance",
  "processing_status": "guidance_ready",
  "received_at": "2026-08-29T00:00:00Z",
  "updated_at": "2026-08-29T00:01:00Z",
  "guidance": {
    "title": "基础指引",
    "steps": [
      {
        "step_id": "read-title",
        "title": "先看标题",
        "instruction": "请你亲自确认页面顶部的标题。",
        "requires_manual_action": true
      }
    ]
  },
  "human_review_reason": null
}
```

`POST` 响应是同一生命周期的收据，并额外返回：

- `image_disposition=discarded_after_validation`；
- `status_endpoint=/api/v1/help-requests/{request_id}`；
- 初始 `processing_status=received`。

响应版本升级为 `1.1`，而上传请求仍是 `1.0`。这是有意把“请求格式”和“结果格式”的演进分开；客户端遇到未知 schema 或未知状态会拒绝解析，而不是猜测。

## 4. 为什么基础指引只有人工步骤

`HelpRequestGuidanceStep` 只有步骤 ID、标题和解释文字，并强制 `requires_manual_action=true`。领域层还会拒绝支付、转账、发红包、密码、验证码、账号删除等危险操作词。它没有：

- Accessibility node ID；
- 屏幕坐标、手势或点击命令；
- 支付、发红包、拉群等不可逆动作参数；
- 可以直接交给 Android Service 执行的函数名。

Android 收到 `guidance_ready` 后只展示说明，并提示用户亲自操作。若未来要继续教程图，仍必须回到现有执行引擎，由页面观察证据验证目标状态；金融和不可逆操作继续由确定性安全策略拦截。模型输出是候选说明，不是执行计划。

## 5. 后端暂存策略

当前没有为求助结果增加数据库表，而是在 `HelpRequestService` 内保存最多 1000 条状态元数据：

```text
accept(request)
  → 校验 Base64、JPEG 标记、大小和 SHA-256
  → bytearray finally 清零
  → 保存 HelpRequestResult（不含图片和问题正文）
```

超过上限时淘汰最早更新时间的结果，查询被淘汰的 ID 返回 404。服务重启后这些结果会消失，这是 MVP 的明确限制；如果将来需要跨重启查询，应新增带 TTL、访问控制和删除策略的 repository，而不是把图片一起持久化。

`threading.Lock` 保护状态字典，因为 FastAPI 同步路由可能在不同线程执行。锁只覆盖短暂的元数据读写，不持有图片，也不包围未来的模型调用。

## 6. Android 查询链路

Android 的边界保持在 `data/`：

```text
ScreenshotHelpViewModel
  → HelpRequestStatusReader（端口）
  → HttpHelpRequestStatusReader（HTTP adapter）
  → GET /api/v1/help-requests/{request_id}
```

发送成功后，`Submitted` 状态只保留脱敏收据和服务端 request ID，图片已经清零。用户点击“刷新处理状态”时，ViewModel 才发起一次查询：

```text
Submitted(received)
  ├─ 查询成功 → Submitted(processingStatus=...)
  └─ 网络/格式失败 → Submitted(statusError=StatusFetchFailed)，仍可重试
```

查询器在拼接 URL 前先校验 request ID 是 UUID；JSON parser 严格检查 `schema_version`、状态枚举、时间字段存在、guidance 与状态的组合，以及每一步的 `requires_manual_action=true`。后端返回未知字段不会被客户端当作执行指令。

UI 状态不把 `processing` 显示成“AI 已回答”：

- `received`：已接收，正在等待处理；
- `processing`：正在处理，暂时不会自动操作手机；
- `needs_human_review`：需要人工复核，已暂停自动生成指引；
- `guidance_ready`：基础指引已生成，请逐步阅读并亲自操作。

## 7. Python/Java 对照

| 本项目 | Java 后端中的常见对应 |
| --- | --- |
| `HelpRequestProcessingStatus` | enum / sealed hierarchy |
| `HelpRequestResult.transition()` | 聚合根的状态迁移方法 |
| `HelpRequestService` | application service |
| `HelpRequestResultResponse` | response DTO / record |
| `HelpRequestStatusReader` | client port / gateway interface |
| `HttpHelpRequestStatusReader` | infrastructure adapter |

Python 的 `StrEnum` 让 JSON 值和业务枚举共用一份定义；不可变 dataclass 防止状态对象在锁外被悄悄修改。Kotlin 端没有依赖服务器生成的代码，而是用 fail-closed parser 保持 Android 与后端契约显式可见，这对逐步学习协议演进很有帮助。

## 8. 测试策略

后端覆盖：

- `POST` 返回 `received` 和状态查询地址；
- `GET` 不回显 Base64 或图片；
- 未知 request ID 返回 404；
- `needs_human_review` 和 `guidance_ready` 的响应形状；
- `received → processing → review/guidance` 的合法迁移；
- 回退、重复迁移和缺少人工步骤均拒绝。

Android JVM 覆盖：

- 收据解析 `schema_version=1.1`、状态枚举和 status endpoint；
- 查询路径 UUID 校验；
- guidance 缺失、未知状态或 `requires_manual_action=false` 时 fail closed；
- ViewModel 刷新后展示 guidance；
- 查询失败保留 `Submitted` 状态并允许重试。

Pixel 7 设备测试继续验证提交结果页和刷新按钮的可见、可点击语义。当前没有真实后台 worker，所以设备上能观察到的初始状态是 `received`。

## 9. 当前限制与下一模块

- 结果元数据暂存在进程内，服务重启后查询不到；
- 没有登录、设备身份、速率限制和家属授权；
- 没有队列、重试或模型 worker，状态迁移入口暂供后续 application worker 使用；
- `guidance_ready` 的文字仍是假设性契约，尚未由 DeepAgent 生成；
- 基础指引仍不能替代教程执行引擎的页面证据和风险拦截。
- 状态查询和未来的 processor 仍需要校验请求 ID、客户端 ID、意图与路由的一致性；客户端不能只相信“格式正确”的 JSON。

下一模块可以实现一个不接真实模型的本地/后台“处理器端口”，让 `processing`、安全复核和结果发布在测试中串起来；确认状态契约稳定后，再评估 DeepAgent、教程检索和人工家属端的接入方式。
