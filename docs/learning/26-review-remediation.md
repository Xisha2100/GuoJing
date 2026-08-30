# 评审修复：安全边界与失败路径收口

本次修复针对模块 10–20 的中期 review，目标不是增加新产品功能，而是把失败、重试和版本漂移路径也纳入同一套安全不变量。

## 1. HTTP 边界先于业务校验

FastAPI 在进入路由函数前就会解析 JSON 和执行 Pydantic 校验。因此，不能只在正常路由里设置 `Cache-Control`，也不能依赖字段长度限制来保护解析阶段。

- `HelpRequestSecurityMiddleware` 在 JSON 解析前限制请求体（12 MiB），同时覆盖可信 `Content-Length` 和 chunked body。
- 统一给求助路径的成功、4xx 和 5xx 响应加 `no-store`/`no-cache`。
- `RequestValidationError` 只返回稳定错误码、字段位置和脱敏消息，不复制 `input`、问题正文或 Base64。

这形成两层资源边界：传输层限制总字节数，领域 DTO 再限制合法图片字段和隐私元数据。

## 2. 状态机异常必须有补偿终态

处理器在 `received → processing` 后可能遇到超时、OCR/模型依赖故障或程序异常。现在异常会统一转成 `needs_human_review`，并使用固定的安全原因；不会把请求永久留在 `processing`，也不会把上游异常详情返回给用户。

重复 POST 始终返回“已接收”收据。收据没有 guidance 字段，因此不能再产生 `guidance_ready + guidance=null` 的非法组合；需要完整结果时使用状态查询接口。

## 3. 人工复核的审计语义

求助结果暂时保存在一个 repository，管理员审计保存在另一个数据库 repository，二者还没有共享 Unit of Work。人工操作因此先写稳定的 `*_requested` 审计事件（`operation_id` 由请求 ID 和动作确定），再改变求助状态。

这样审计写入失败时不会先产生未审计的发布状态；同时操作 ID 为将来 transactional outbox 或补偿重放保留关联点。当前事件准确表示“管理员发起了请求”，不虚构跨 repository 的原子“已成功发布”。

## 4. Android 请求与收据的关联

脱敏副本进入 `Ready` 时生成一次 `clientRequestId`，发送失败回到同一个 `Ready` 后仍复用该 ID。发送器严格检查：

- response 的 `client_request_id` 等于本地 ID；
- `intent` 与 route 的确定性映射与本次提交一致；
- `request_id` 是 UUID；
- `status_endpoint` 是该 request ID 的固定相对路径；
- 初始 POST 收据状态必须是 `received`。

状态查询继续校验请求 ID、客户端 ID、意图和 route，任何错配都 fail closed。

## 5. 版本漂移和浮层生命周期

视觉匹配不再等同于“可以复用教程”。`assessVersionCompatibility` 单独判断：同一已验证版本、新版本、已存储 stale 和未知版本号。新版本只允许低风险步骤试运行，并强制观察两个连续的目标页证据；金融和不可逆步骤不会因版本漂移自动通过。

浮层命令现在携带 graph/node/observation sequence。AccessibilityService 在显示前必须看到同一序列的 `Available` 观察；无 root、构建观察失败、隐私暂停、切换应用和 Service 重连都会立即隐藏，重连后必须等待新观察。

## 6. OCR 和隐私不变量

OCR builder 对 block 做一对一分配，并要求子串有足够覆盖率；短公共词不能同时满足多个锚点。`ScreenshotSanitizationReceipt`、ViewModel setter 和 `canSanitize` 三层共同保证：

```text
redactionCount == 0  ⇔  noSensitiveContentConfirmed == true
redactionCount > 0   ⇔  noSensitiveContentConfirmed == false
```

指引总标题、步骤标题和正文使用同一归一化危险词策略（去空格/标点并覆盖支付、转账、删除、密码、验证码等同义表达）。

## 7. 学习要点与后续演进

这组改动展示了“正常路径测试”之外的三类工程验证：资源边界测试、故障补偿测试和跨组件关联测试。生产化时仍应把求助状态与审计迁移到同一 Unit of Work 或 transactional outbox，并在真实设备上补 Service 重建、无 root 和版本更新的 UI/系统测试。
