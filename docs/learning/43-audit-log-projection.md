# 模块 43：审计日志投影

`ProcessingAuditEvent.as_log_fields()` 是唯一的日志/Outbox 投影：输出 request ID、worker、action、时间和尝试次数。由于领域对象从一开始没有用户内容字段，投影也不会在重构时意外复制截图或 OCR。
