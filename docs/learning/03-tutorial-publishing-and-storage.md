# 03：教程草稿发布与读取

## 1. 这一模块解决了什么

模块 01 只回答“一个教程在内存中如何表示和校验”。本模块把它变成第一个可部署的垂直切片：

```text
管理网页（未来）
  → POST 草稿
  → Pydantic DTO
  → TutorialService
  → 领域图校验
  → Repository Protocol
  → SQLAlchemy / SQLite
  → 人工发布某个修订
  → Android GET 已发布教程
```

这里最重要的产品规则不是 CRUD，而是：

- 草稿可以反复保存，旧修订不能被覆盖。
- 发布必须明确选择一个修订。
- Android 永远看不到未发布草稿。
- 没有管理员令牌时，写接口默认关闭。
- 教程图仍由领域层校验，数据库和 HTTP 不能绕过规则。

## 2. 分层：依赖为什么要朝内

源码现在分成四类：

```text
api ───────────────┐
                   ↓
application ───→ domain
     ↑
infrastructure
```

- `domain`：教程节点、转移、页面锚点和校验规则，只依赖 Python 标准库。
- `application`：组织“保存草稿、发布、读取”用例，并声明需要什么 Repository。
- `infrastructure`：用 SQLAlchemy 实现 Repository。
- `api`：把 HTTP JSON、Bearer Token、状态码翻译成应用层调用。
- `main.py`：组合具体实现，是 composition root。

如果用 Java/Spring 类比：

| 本项目 | Java 常见角色 |
|---|---|
| `TutorialGraph` | Domain Entity / Value Object |
| `TutorialService` | `@Service` 应用服务 |
| `TutorialRepository` Protocol | Repository interface / port |
| `SqlAlchemyTutorialRepository` | JPA Repository adapter |
| FastAPI route | `@RestController` |
| `create_app()` | Spring configuration / bean wiring |

Python 的 `Protocol` 是结构化类型：实现类不必显式 `implements`，只要方法签名匹配，mypy 就认为它满足端口。这和 Java 名义类型不同，但目标相同——应用层不依赖数据库实现。

## 3. 为什么 DTO 不直接等于领域对象

HTTP 与数据库中的教程文档使用 `TutorialGraphDto`，领域规则使用冻结的 dataclass `TutorialGraph`。两者通过 `to_domain()` 和 `from_domain()` 显式转换。

这么做看起来重复，但隔离了三种变化：

1. API 字段校验和 OpenAPI 描述属于 Pydantic。
2. 领域对象不应该依赖 Pydantic、FastAPI 或 JSON。
3. 将来 API schema 升级时，可以保留旧 DTO 并映射到同一领域模型。

DTO 包含固定的 `schema_version: "1.0"`，并设置 `extra="forbid"`。如果 Android 或管理端发送未知字段或未知版本，服务会明确拒绝，而不是悄悄丢数据。

Pydantic 负责字段级问题，例如坐标范围、字符串非空和枚举值；`validate_tutorial_graph()` 继续负责跨对象问题，例如起点是否存在、节点是否可达、目标锚点是否合法。这类似 Bean Validation 与领域校验的区别。

## 4. 数据模型：修订和发布为什么分开

数据库有三张表：

```text
tutorials
  graph_id PK
  package_name

tutorial_revisions
  revision_id PK
  graph_id FK
  revision_number
  graph_json

tutorial_publications
  graph_id PK/FK
  revision_id UNIQUE/FK
  published_at
```

`tutorial_revisions` 是 append-only：每次保存产生 1、2、3……的新修订，图快照以版本化 JSON 保存。`tutorial_publications` 只有一个可移动指针，指出当前公开的是哪个修订。

它优于在 `tutorials` 表放 `status=published` 的原因：

- 发布修订 2 后仍能回退到修订 1。
- Android 的一次读取对应完整、不可变快照。
- 编辑草稿不会意外改变线上教程。
- 后续可以审计“谁在何时发布了什么”。

这里没有把每个 node/anchor/transition 全部拆成关系表。MVP 的主要读写单位是整个状态图，JSON 快照让一致性和版本演进更简单；需要跨教程查询锚点时再评估规范化。

## 5. 事务边界

Repository 的每个写方法都使用：

```python
with session, session.begin():
    ...
```

这意味着保存修订、移动发布指针要么全部成功，要么全部回滚。`Session` 不跨请求共享，因为 SQLAlchemy Session 类似 JPA `EntityManager`：它表示一个工作单元，不是线程安全的全局连接。

本模块使用同步 SQLAlchemy：

- SQLite 标准驱动是同步的。
- MVP 只有一个管理员，写入频率低。
- 普通 FastAPI `def` 路由会在线程池执行。
- 使用异步 ORM 不会让 SQLite 获得并行写能力，却会增加生命周期和测试复杂度。

如果未来换 PostgreSQL 且出现大量并发 I/O，再用指标决定是否引入 asyncpg/AsyncSession。

当前修订号通过事务内查询 `max(revision_number) + 1` 生成，适合单管理员 MVP。多管理员同时保存同一教程时，唯一约束能阻止重复，但其中一个请求可能失败；届时应改为数据库序列、原子计数或捕获冲突后重试。

## 6. SQLite 的几个关键设置

运行时连接会设置：

- `PRAGMA foreign_keys=ON`：SQLite 默认可能不执行外键约束，必须按连接启用。
- `PRAGMA busy_timeout=5000`：短暂写锁竞争时等待最多 5 秒，而不是立即失败。
- `journal_mode=WAL`：由 migration/bootstrap 显式启用，让读请求不容易被写事务阻塞。

SQLAlchemy 2 对文件型 SQLite 已有适合 Web 请求的连接池行为，并默认处理跨线程连接参数，所以代码没有重复写 `check_same_thread=False`。

SQLite 读取 `DateTime(timezone=True)` 时可能返回没有 `tzinfo` 的值，Repository 在跨出适配器边界前统一补成 UTC。这样 API 始终输出带时区的 RFC 3339 时间。

## 7. Alembic：为什么不用 `create_all()`

`Base.metadata.create_all()` 只能说“缺表就建表”，不能可靠表达生产数据库从版本 A 到版本 B 如何变化，也不记录执行历史。

Alembic migration 是数据库结构的版本控制：

```bash
uv run alembic upgrade head
```

首次迁移创建三张业务表和 `alembic_version`。迁移文件同时有 `upgrade()` 和 `downgrade()`，测试会从空数据库升级到 head，再降级到 base。

测试 Repository 时使用 `create_all()` 是允许的，因为那只是快速创建隔离测试夹具；部署路径必须走 Alembic。这个区别类似生产使用 Flyway/Liquibase，而单元测试可以用 ORM schema generation。

## 8. 管理 API 的安全边界

配置项 `GUOJING_ADMIN_API_TOKEN` 使用 Pydantic `SecretStr`：

- 少于 32 字符时启动配置校验失败。
- `repr(settings)` 不会打印明文。
- 比较令牌使用 `hmac.compare_digest()`，避免普通字符串比较的时序差异。
- 没配置时写接口返回 503，而不是以无认证模式启动。

这是一个单管理员 MVP 的 bootstrap 方案，不是最终身份系统。它缺少用户、密码哈希、会话撤销、TOTP、操作审计和 CSRF 设计。管理网页接入前应建立真正的认证模块。

只读接口仅返回发布表指向的修订，因此即使知道 `graph_id` 也不能读取草稿。

## 9. HTTP 合约

```text
POST /api/v1/admin/tutorials/drafts
POST /api/v1/admin/tutorials/{graph_id}/revisions/{revision_number}/publish
GET  /api/v1/tutorials
GET  /api/v1/tutorials/{graph_id}
```

重要状态码：

- `201`：草稿修订已创建。
- `401`：管理员令牌错误。
- `404`：教程或公开修订不存在。
- `409`：同一 `graph_id` 被用于不同 Android package。
- `422`：DTO 或领域图无效。
- `503`：管理 API 尚未配置令牌。

领域图的 `422` 会一次返回所有独立问题，包括稳定的 `code`、`node_id` 和 `transition_id`。未来网页编辑器可以直接定位并标红错误，而不必解析英文 message。

## 10. 测试分层

本模块新增测试覆盖：

- DTO ↔ domain 无损往返和 schema 拒绝策略。
- 真实 SQLite 中修订只增不改、发布与重新发布。
- 草稿不会出现在公开列表。
- graph/package 身份冲突。
- 从空数据库 upgrade、再 downgrade。
- 管理令牌的关闭、错误与成功路径。
- 从 HTTP 保存草稿、发布、公开读取的完整流程。
- 原有领域和健康检查回归。

完整命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
```

## 11. 你可以动手验证

先设置仅存在于当前 shell 的随机令牌并迁移：

```bash
export GUOJING_ADMIN_API_TOKEN="$(openssl rand -hex 32)"
uv run alembic upgrade head
uv run uvicorn guojing.main:app --reload
```

然后访问 Swagger UI：<http://127.0.0.1:8000/docs>。可以观察：

1. 不带 Bearer Token 保存草稿会得到 401。
2. 草稿保存成功后，`GET /api/v1/tutorials` 仍为空。
3. 明确发布 revision 1 后，公开列表才出现教程。
4. 再保存 revision 2 不会改变公开内容，直到显式发布 revision 2。

## 12. 留给下一模块的问题

下一模块将讨论“录制/编辑工作流”，重点不是马上画网页，而是先定义：

- 截图、Accessibility 节点和 OCR 如何形成候选锚点。
- 管理员怎样修改 required / optional / forbidden。
- 如何分步骤保存未完成草稿。
- AI 如何提出建议但不能越过人工发布。
- 图片等大文件如何与教程 JSON 分开存储。

确认本模块后再进入下一模块。
