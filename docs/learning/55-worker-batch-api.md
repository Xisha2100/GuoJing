# 模块 55：Worker 批处理 API

`POST /api/v1/admin/help-requests/process-next` 让本地 MVP 通过一个受保护的管理端调用运行有限批次。它复用队列、租约前的 claim 组合和正式工作流；请求正文、截图和 OCR 不会出现在响应中。

长期部署可把这个入口换成 cron 或消息队列消费者，处理规则不需要迁移到 HTTP 层。
