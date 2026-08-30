# 模块 38：处理审计事件

`ProcessingAuditEvent` 只允许 request UUID、worker ID、短 action 名、时间和尝试次数。它没有 payload、问题正文、图片、OCR 或模型响应字段。

这是一条重要的日志边界：可观测性需要回答“何时由谁处理到哪一步”，不需要复制用户数据。后续 outbox/repository 可持久化此值对象并按 request ID 关联管理员审计。
