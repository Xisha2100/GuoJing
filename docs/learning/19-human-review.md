# 模块 19：管理员人工复核闭环

## 1. 目标

处理器遇到缺少证据或安全不确定的请求时必须停下。本模块复用已有管理员登录、会话 Cookie、CSRF 和审计机制，让人工可以读取待复核元数据并发布一份安全的人工指引。

## 2. HTTP 接口

```text
GET  /api/v1/admin/help-requests/reviews
POST /api/v1/admin/help-requests/{request_id}/guidance
```

列表返回有长度上限的问题正文以及 UUID、路由、状态、时间和复核原因；它不返回截图、Base64 或 OCR。发布请求使用严格的标题和 1–20 个步骤模型。

## 3. 权限与审计

两个接口都需要管理员会话和 CSRF 双提交证明。状态变更前先写入
`help_request.process_requested` 或 `help_request.guidance_publish_requested` 审计事件，
并带有由请求 ID 推导的稳定 `operation_id`。这样审计仓库故障时状态不会先改变；
由于求助结果与审计目前不共享事务，这里审计的是管理员发起的请求，而不是假装
“已经成功发布”。未来引入 Unit of Work 或 transactional outbox 后，再增加可证明
成功的完成事件。

## 4. 为什么领域层仍要校验

即使网页已经隐藏危险按钮，HTTP 客户端仍可能绕过网页直接调用接口。因此危险操作词检查放在 `HelpRequestGuidanceStep`，接口只负责把领域异常映射成 422；状态不允许时返回 409。

## 5. 后续扩展

当前是最小管理员工作台接口，没有复杂家属账号、图片回看或多人审批。要增加家属端，应先增加请求归属、授权和可撤销访问令牌，再把同一只读结果投影给网页。
