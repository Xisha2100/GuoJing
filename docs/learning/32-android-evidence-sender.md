# 模块 32：Android Evidence Envelope 与发送器

## 目标

后端已有严格的证据 API，但 Android 之前只会发送脱敏截图求助，无法把当前页面的结构锚点用于教程匹配。本模块补齐客户端的数据合同和 HTTP sender。

## 证据内容

`HelpRequestEvidenceSubmission` 只包含：请求 ID、稳定 evidence ID、目标包名及版本、来源、结构分、锚点 ID/置信度/归一化边界和时间戳。它不包含 OCR 原文、Accessibility 节点文本、截图 URI、像素或可执行坐标。

从 `ScreenObservation` 转换时，只有 `SanitizedNetworkAllowed` 可以通过；`LocalOnly` 会直接在 Android 端抛出异常，不存在“先传上去、再让后端拒绝”的隐私窗口。evidence ID 由调用方保留，因此同一网络重试可复用同一个 ID。

## 调用链

```text
ScreenObservation
  -> HelpRequestEvidenceSubmission.fromObservation
  -> HttpHelpRequestEvidenceSender
  -> POST /help-requests/{request_id}/evidence
```

sender 会严格核验响应的 `request_id`、`evidence_id`、schema 和联网分享策略，防止错误响应被当作当前会话证据。模块 35 将把该 sender 接入实际求助 UI 和教程执行闭环。

## 验证

JVM 测试验证了 JSON 中只有结构锚点字段、不会出现文本或 OCR 字段，并覆盖 `local_only` 拒绝与稳定 ID 的映射。这里的 Kotlin `data class` 相当于后端 Pydantic DTO；两端各自验证是纵深防御，而不是重复劳动。
