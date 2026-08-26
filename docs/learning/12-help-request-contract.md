# 模块 12：截图求助请求契约与显式发送

## 1. 本模块解决的问题

模块 11 只能在手机本机生成脱敏副本，用户看得到“图片已经遮住了”，但还没有一个明确的联网边界。本模块补上这一段：

```text
本机脱敏副本
  → 用户选择求助意图
  → 用户明确确认只发送脱敏副本
  → 严格 JSON 请求
  → 后端校验摘要与大小
  → 立即丢弃临时图片
  → 返回处理分支收据
```

这里仍然不接 OCR、视觉模型、数据库、对象存储或 DeepAgent。服务端返回 `accepted_no_model`，表示“请求已通过协议校验”，不是“AI 已经回答”。把这两件事分开，后续出现模型错误时不会误以为上传链路已经可靠。

## 2. 为什么本模块暂时使用 JSON Base64

生产图片上传通常会选择 `multipart/form-data` 或对象存储预签名 URL。它们各有优点，但 FastAPI 的 multipart 解析需要新增 `python-multipart` 依赖，预签名 URL 又需要真实对象存储和生命周期配置。

当前 MVP 采用已有能力就能完成的 `application/json`：

```json
{
  "schema_version": "1.0",
  "client_request_id": "uuid",
  "intent": "recorded_tutorial",
  "question": "下一步应该点哪里?",
  "image_media_type": "image/jpeg",
  "image_width": 720,
  "image_height": 1440,
  "redaction_count": 1,
  "no_sensitive_content_confirmed": false,
  "sanitized_sha256": "...64 个十六进制字符...",
  "send_consent": true,
  "sanitized_image_base64": "/9j/..."
}
```

Base64 会让图片大约增加三分之一体积，因此它不是最终的大规模上传方案。它适合当前阶段学习和验证：无需安装新包，无需数据库迁移，Android 和 Python 可以直接测试完整 HTTP 契约。进入真实用户规模前，应重新评估 multipart、分片、压缩、超时和对象存储生命周期。

## 3. 契约如何表达安全意图

`HelpRequestRequest` 不是一个“随便放几个字段的字典”，而是服务端的防腐层。它拒绝额外字段，并限制：

- `schema_version` 只能是 `1.0`；
- `intent` 只能是 `recorded_tutorial` 或 `general_guidance`；
- 问题长度为 1 到 300；
- 媒体类型只能是 `image/jpeg`；
- 声明的宽高都不超过 1440，最多 20 个遮挡区域；
- 没有遮挡区域时必须有明确的 `no_sensitive_content_confirmed=true`；
- 有遮挡区域时不能同时声明“没有敏感内容”；
- `send_consent` 是 `Literal[True]`，缺失或 `false` 都会得到 422；
- SHA-256 必须是 64 位小写十六进制摘要。

这和 Java 后端中使用 Bean Validation 注解、再映射成不可变 Command 类相同。Pydantic DTO 负责 HTTP 语法，`HelpRequestCommand` 负责框架无关的业务不变量，避免把 FastAPI 类型泄漏进 domain。

## 4. 两条路由不是让 Agent 猜出来的

Android Ready 页面要求用户二选一：

```text
查找已录制教程       → tutorial_match
没有教程，先看基础指引 → general_guidance
```

后端只做确定性映射：

```python
if intent == RECORDED_TUTORIAL:
    route = TUTORIAL_MATCH
else:
    route = GENERAL_GUIDANCE
```

未来的 Agent 可以在 `tutorial_match` 分支中调用教程检索，在 `general_guidance` 分支中生成基础解释，但不能偷偷把一个用户选择改成另一个分支。对 Python Agent 开发而言，这相当于把 route 作为 graph state 的受约束枚举，而不是在 prompt 中约定一段容易漂移的自然语言。

## 5. 客户端的显式发送状态机

模块 11 的 `Ready` 状态现在增加了意图、发送确认和错误信息：

```text
Ready
  ├─ 未勾选同意 → 发送按钮 disabled
  ├─ 勾选同意 → Sending
  ├─ 网络失败 → Ready(error=SendFailed)，副本仍可重试
  └─ 收到收据 → Submitted，不再持有图片
```

`ScreenshotHelpViewModel` 只在 Ready 状态接受 `send()`，UI 回调不能绕过这个门槛。发送成功后调用 `erase()`，`Submitted` 只保留问题、处理收据和摘要元数据。发送失败则保留脱敏副本，让用户重试，而不会退回到原始截图。

这和 Java 后端的 application service 状态转换类似：Controller 不直接改变状态，ViewModel/service 才是状态机所有者。取消、返回和 ViewModel 销毁仍会清理 Sending 中的图片。

## 6. Android 网络适配器

网络边界放在 `data/`：

```text
ScreenshotHelpViewModel
  → HelpRequestSender（端口）
  → HttpHelpRequestSender（适配器）
  → HttpJsonClient.postJson()
  → POST /api/v1/help-requests
```

`HelpRequestSender` 让 JVM 测试可以注入 Fake，不需要启动服务器。真实适配器负责：

1. 生成 `client_request_id`；
2. 从内存 JPEG 生成 Base64；
3. 写入与 Python DTO 相同的字段名和值；
4. 解析服务端收据；
5. 对 HTTP 非 2xx 和格式异常统一失败。

它不负责决定是否可以发送，也不负责擦除图片。发送权限由 ViewModel 门控，生命周期清理由 ViewModel 所有，这样每个组件的责任单一且可测试。

## 7. 后端为什么不保存图片

`HelpRequestService.accept()` 的处理过程是：

```text
Base64 字符串
  → bytearray
  → 校验长度、JPEG 起止标记、SHA-256
  → 生成 receipt
  → finally 用零覆盖 bytearray
```

数据库模型和对象存储适配器都没有加入本模块。响应只包含：

- 服务端 request ID；
- 客户端 request ID；
- 用户选择的意图；
- 下一步处理分支；
- `accepted_no_model`；
- `discarded_after_validation`；
- 接收时间。

这不是“永久保密”的证明。Python 字符串不可变，JSON 解析和网络栈也可能有临时副本；应用日志、反向代理和崩溃转储也需要单独配置。当前实现能保证的是：业务层没有把图片写入 SQLite、对象存储或响应体，并且对服务层创建的可变缓冲区做了 best-effort 清理。

## 8. SHA-256 能证明什么

客户端在模块 11 的本地脱敏结果中已经有 SHA-256。模块 12 把摘要和图片一起发送，服务端重新计算：

```text
sha256(received_bytes) == sanitized_sha256
```

这能发现传输内容与客户端声明不一致，也能让未来的上传收据关联到“哪一份脱敏副本”。它不能证明遮挡区域选择正确，也不能证明图片里没有遗漏隐私。摘要不是内容安全扫描，也不是用户身份认证。

## 9. 当前接口的安全与产品限制

本模块明确留下几项限制，避免把 MVP 协议误当生产方案：

- 接口目前没有登录、设备身份、速率限制或配额，真实部署前必须增加滥用防护。
- 服务端只检查 JPEG magic bytes 和客户端声明的尺寸，没有引入完整 JPEG 解码器重新测量像素尺寸；后续 OCR/视觉服务接入前必须在隔离 worker 再次解码和限制资源。
- Base64 增大请求体，不能直接用于大规模长截图。
- 接收成功不代表已经得到答案；当前没有队列、重试、模型调用或结果查询接口。
- `client_request_id` 目前只用于关联收据，没有持久化，因此暂不提供跨重试的幂等查询。

把这些限制写在协议文档里，比在 UI 上显示“正在分析”更诚实，也方便后续逐项补齐。

## 10. 测试策略

后端测试覆盖：

- 合法脱敏 JPEG 返回 202 和路由收据；
- 已录制教程与基础指引路由分离；
- 摘要不匹配、缺失发送同意、隐私元数据冲突、非法 Base64 均拒绝；
- 响应不回显图片内容。

Android JVM 测试覆盖：

- HTTP `POST` URL、Content-Type、字段和值；
- 发送按钮的同意门槛；
- 成功后清零图片；
- 失败后保留图片并允许重试。

Pixel 7 设备测试继续覆盖截图入口和 Compose 页面。完整验证命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check

cd android
./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest
./gradlew connectedDebugAndroidTest
```

## 11. 下一模块

下一模块先评估截图内容解析方案，再决定引入哪一种模型能力：

1. Android 本地 OCR：隐私最小、离线可用，但需要评估中文识别、包体和设备性能。
2. 后端 OCR：便于统一升级和审计，但需要传输图片并承担服务端数据边界。
3. 多模态视觉服务：可以直接理解界面和问题，但成本、延迟、数据出境和回答可验证性更复杂。

选择后会先向项目所有者说明需要安装的依赖、服务账号、网络和成本，再实现一个可替换端口。无论选择哪种方案，模型输出都只能成为教程匹配或基础解释的候选证据，不能直接执行微信支付、红包、拉群或其他金融/不可逆操作。
