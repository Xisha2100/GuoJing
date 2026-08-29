# 模块 21：求助结果持久化与 TTL

## 1. 为什么要做这一模块

模块 16–20 的结果状态保存在 Python 进程内存中。服务重启、多个 Uvicorn worker 或部署滚动更新都会让客户端查询不到结果。本模块把“状态对象如何保存”抽成 Repository，并让默认 API 使用 SQLite。

## 2. 分层设计

```text
HelpRequestService
  → HelpRequestRepository（application port）
      ├─ InMemoryHelpRequestRepository（单元测试）
      └─ SqlAlchemyHelpRequestRepository（SQLite/PostgreSQL 边界）
```

业务服务仍负责校验输入和状态迁移，Repository 负责查询、保存、幂等和过期清理。这个边界对应 Java 中的 Repository interface + JPA/SQL adapter；领域对象不导入 SQLAlchemy。

## 3. 数据库保存什么

`help_request_results` 表只保存：请求 UUID、客户端幂等 UUID、请求指纹、路由、状态、时间、TTL、人工复核原因和已审核指引 JSON。截图字节、Base64、URI 和问题正文都不会进入表。

指引 JSON 是受领域对象约束后的有限投影，而不是任意模型响应。读取时重新构造 `HelpRequestGuidance`，因此数据库中的危险文案也不能绕过领域校验。

## 4. TTL 与容量

默认结果 TTL 为 24 小时。创建、单条读取和列表读取都会删除 `expires_at <= now` 的记录。Repository 同时保留容量上限，超出时淘汰最早更新时间的元数据；这是 MVP 的资源保护，不等同于永久存档。

生产环境仍应增加定时清理任务、监控和可配置的保留策略。TTL 不应依赖客户端是否继续轮询。

## 5. 跨进程幂等

`client_request_id` 在数据库中有唯一约束。服务端保存的是不含原文的问题哈希、图片尺寸、脱敏数量和图片摘要组成的指纹：同一请求重试会返回原收据，不同内容复用同一 ID 会报错。内存实现与 SQL 实现共享这一行为合同。

## 6. 迁移与启动

新增 Alembic revision `20260830_04_create_help_request_results`。正式启动仍应先执行 `uv run alembic upgrade head`；测试用 `Base.metadata.create_all` 创建隔离 schema。`create_app` 的默认 composition root 将 SQL Repository 注入服务，测试可以显式传入内存或独立数据库实现。

## 7. 限制和下一步

本模块解决了状态的跨重启保存，但尚未解决请求归属、家属授权、队列和 PostgreSQL 部署。下一模块会定义受控证据 Envelope，讨论在不恢复原图长期存储的前提下，如何让本地 OCR 摘要进入处理器。

