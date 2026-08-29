# 模块 22：受控证据 Envelope 与隐私边界

## 这一模块解决什么问题

截图已经在 Android 本地完成脱敏，但后端处理器还需要知道“当前是什么页面”。如果直接上传 OCR 原文、Accessibility 节点树或图片字节，隐私边界会重新变得模糊。本模块把可共享信息收敛为一个短时有效的 `EvidenceEnvelope`：应用包名和版本、结构分数、锚点 ID、置信度和归一化边界。

Envelope 的类型中没有 `text`、`ocr_text`、节点树或图片字节字段，因此调用方无法通过这个端口把原文偷偷带进处理器。`local_only` 证据在网络服务入口会 fail closed；只有明确标记为 `sanitized_network_allowed` 且未过期的摘要可以提交。

## 调用链

```text
Android OcrObservationBuilder
  -> anchor_id / confidence / normalized_bounds
  -> HelpRequestEvidenceRequest (schema_version=1.0)
  -> HelpRequestEvidenceService
  -> EvidenceEnvelope.require_network_allowed()
  -> SQLite help_request_evidence
```

证据与求助结果分表保存。求助结果过期后，外键级联删除其证据；证据自身也有 `expires_at`，每次读写先清理过期行，并受数量上限约束。

## 关键技术点

### 不可变值对象

Python `@dataclass(frozen=True, slots=True)` 类似 Java 的 `record`：创建后不能修改，也不会意外挂载额外字段。`__post_init__` 集中检查时间、坐标、置信度、锚点数量和重复 ID。

### 显式隐私策略

`EvidenceSharingPolicy` 不是提示词，而是领域枚举。服务端收到 `local_only` 时直接拒绝；这使得“不能上传”成为代码路径上的约束，而不是依赖客户端自律。

### 短期证据

Envelope 只服务于一次求助处理。`expires_at` 防止旧版本页面证据长期复用，也降低误存数据的影响面。SQLite Repository 与内存替身实现相同的清理语义，便于无 I/O 单元测试。

### 数据库迁移

新增 Alembic revision `20260830_05`，并在 SQLAlchemy `Base.metadata` 中加入对应映射。生产启动前仍需执行 `uv run alembic upgrade head`；测试使用临时 SQLite `create_all`，确保 API 测试不会触碰开发数据库。

## 与已有处理器的关系

本模块只接收和保存证据，不改变 `HelpRequestService` 的状态迁移规则。后续教程检索模块会把 Envelope 转换为确定性的页面匹配输入；匹配失败仍然只能停在 `needs_human_review`，不能由证据直接触发点击或支付。

## Java/Python 对照

| Python | Java/Kotlin 对照 |
| --- | --- |
| `Protocol` Repository | interface / port |
| frozen dataclass | Java record / Kotlin data class（只读属性） |
| `StrEnum` | enum class |
| Pydantic `extra="forbid"` | kotlinx.serialization 严格解析 + unknown key fail |
| SQLAlchemy Session | JPA EntityManager / DAO 的短事务 |

## 当前取舍与后续扩展

目前只保留锚点摘要和版本信息，不保存 OCR 原文；`sanitized_screenshot_sha256` 仅用于完整性关联，不代表服务端保存图片。后续若需要上传一张脱敏图，应继续沿用“单独显式同意、大小限制、单次处理、处理后清零”的协议，不把图片塞进 Envelope JSON。
