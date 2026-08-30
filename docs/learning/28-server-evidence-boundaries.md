# 模块 28：服务端证据时间与保留边界

## 目标

模块 22 定义了 `EvidenceEnvelope`，但客户端提供的 `captured_at` 与 `expires_at` 不能作为服务端排序和留存的可信依据。本模块把这些边界收回到服务端，避免设备时间错误或恶意时间戳让旧证据长期可见、覆盖较新的证据，或无限堆积。

## 实现

`HelpRequestEvidenceService` 在写入时统一转为 UTC，并执行以下规则：

1. `captured_at` 最多比服务器当前时间早 15 分钟，最多领先 30 秒。
2. 服务端计算 `now + 10 分钟`，将其与客户端声明的过期时间取较早者；客户端不能延长证据保留期。
3. 读取最新证据前先确认父 `HelpRequestResult` 仍存在；求助过期后，关联证据不能再通过 API 读取。
4. Repository 持久化 `received_at`，按服务器接收顺序而不是客户端采集时间选择“最新”。
5. SQL Repository 还按每个求助最多保留 8 条、全局最多 1000 条清理记录；同一 `evidence_id` 只允许重试相同提交，不能被不同内容覆盖。

配置位于 `Settings`：`HELP_REQUEST_EVIDENCE_MAX_AGE_MINUTES`、`HELP_REQUEST_EVIDENCE_TTL_MINUTES`、`HELP_REQUEST_EVIDENCE_FUTURE_SKEW_SECONDS` 和 `HELP_REQUEST_EVIDENCE_MAX_PER_REQUEST`。默认值适合 MVP；生产环境应根据网络延迟和存储预算调整，而不是把它们取消。

迁移 `20260830_07_harden_help_request_evidence` 为已有记录补写 `received_at`（使用历史 `captured_at` 作为不可恢复的近似），再创建接收时间索引。新数据不会再依赖该近似值。

## 调用链

```text
Android 已脱敏 EvidenceEnvelope
  -> POST /help-requests/{id}/evidence
  -> HelpRequestEvidenceService.record
       -> 时间窗口、网络分享策略、父请求检查
       -> 服务器 TTL 截断
       -> SQL Repository（received_at + 有界清理）
  -> 202 响应中返回实际生效的 expires_at
```

这里的 `received_at` 类似 Java 服务中数据库的 `created_at`：它描述“服务器何时接受了事件”，比客户端的业务发生时间更适合作为并发排序基准。客户端的 `captured_at` 仍保留，用来判断截图是否足够新，但不再决定覆盖顺序。

## 验证与取舍

新增测试覆盖服务端 TTL 截断、未来采集时间拒绝、按接收顺序读取，以及父请求过期后的隐藏；HTTP 测试也确认响应不会接受一天的客户端 TTL。

本模块不保存原始截图、URI、OCR 文字或可识别的界面节点。`EvidenceEnvelope` 仍只保存结构锚点和可选的已脱敏截图摘要。时间校验不是隐私替代品：Android 端仍必须在选择图片、局部擦除和显式发送确认后才调用接口。
