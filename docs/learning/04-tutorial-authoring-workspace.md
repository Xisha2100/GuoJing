# 04：教程录制与编辑工作区

## 1. 为什么正式教程修订还不够

模块 03 的 `TutorialGraphDto` 是一个严格的发布候选：必须有 graph id、标题、APP 身份、起点、完整节点和转移，而且整个图必须通过结构校验。

真实录制过程却天然是不完整的：

1. 先记录一个页面截图或 Accessibility Tree。
2. OCR、规则或 AI 提出候选锚点。
3. 管理员选择 required、optional、forbidden。
4. 再录制下一页和用户动作。
5. 最后补标题、起点和版本信息。

如果每次保存都要求形成合法 `TutorialGraph`，管理网页只能把半成品存在浏览器里。一旦刷新或换电脑，工作就会丢失。因此本模块增加一种独立对象：`TutorialDraftDocument`。

```text
不完整 TutorialDraftDocument
          │
          │ validate / 人工修改
          ▼
完整且合法 TutorialGraph
          │
          │ promote（提升）
          ▼
未发布 TutorialRevision
          │
          │ publish（另一个明确操作）
          ▼
Android 可见 PublishedTutorial
```

“提升”和“发布”故意是两个动作。即使 AI 帮助产生了完整图，也只能进入待审核修订，不能直接影响老年用户。

## 2. 两种模型，而不是大量 Optional 污染正式模型

本模块没有把原来的 `TutorialGraph` 所有字段改成 `Optional`。那会让运行时匹配、发布和 Android 读取到处处理 `None`，破坏模块 01 已建立的领域不变量。

我们新增：

- `DraftTutorialGraph`：顶层元数据可以缺失，节点和转移可以逐步加入。
- `TutorialDraftDocument`：包含部分图和录制证据。
- `build_tutorial_graph()`：负责从草稿跨越到正式领域对象。

转换分两阶段报告问题：

1. 草稿完整性，例如 `missing_title`、`missing_start_node`、`no_nodes`。
2. 正式图结构，例如重复节点、不可达节点、目标锚点错误。

这类似 Java 中把 `TutorialDraftCommand` 与强不变量的 `Tutorial` Aggregate 分开，而不是让 Aggregate 在大部分生命周期里处于非法状态。

## 3. 录制证据协议

一个 `ScreenCapture` 可以关联三类大文件：

- `screenshot`
- `accessibility_tree`
- `ocr_result`

工作区 JSON 不直接保存图片、XML 树或 OCR 全文，只保存：

```text
artifact_id + kind + sha256
```

原因有四个：

- JSON 和数据库行不会被大图片撑大。
- 文件生命周期可以由将来的 Asset Service 独立管理。
- `sha256` 能发现文件被替换或传输损坏。
- 数据库备份与对象存储备份可以采用不同策略。

当前模块只定义引用协议，没有实现上传接口，也没有真实存储这些文件。管理网页和文件存储接入前，不能把任意 `artifact_id` 理解成已存在文件。

## 4. `sanitized` 与 `local_only`

教程录制通常应使用测试账号和虚构联系人，并在上传前脱敏。`CaptureSharingPolicy` 有两个值：

- `sanitized`：允许后端保存资源引用和候选锚点。
- `local_only`：后端只能知道存在这次采集，不允许携带 artifact 或 candidate 内容。

该规则同时存在于 Pydantic DTO 和领域 dataclass：

- DTO 在 HTTP 边界返回清晰的 `422`。
- 领域规则保证其他调用者绕过 HTTP 时仍不能构造非法对象。

运行时教程节点的 `PrivacyMode.LOCAL_ONLY` 与录制素材的 `CaptureSharingPolicy` 不是同一概念。前者表示真实老人操作该页面时必须本地处理；后者表示用于制作教程的这份素材是否已经脱敏并获准进入后端。支付页面运行时必须 local-only，但可以使用完全虚构的演示账号制作 sanitized 教程素材。

## 5. 候选锚点与人工复核

`AnchorCandidate` 记录候选来源：

- `accessibility`
- `ocr`
- `manual`
- `ai`

以及决策：

- `proposed`
- `accepted`
- `rejected`

规则是：

- proposed 不能声称已有 reviewer。
- accepted/rejected 必须有 `reviewed_by`。
- capture、artifact、candidate ID 必须唯一，避免网页命令指向歧义对象。

当前 `reviewed_by` 仍基于单管理员 Bearer Token 语境，不能证明真实自然人身份。下一认证模块会让它来自服务端登录会话，而不是相信浏览器随意填写。

更重要的安全边界在流程末端：候选无论来自 AI 还是人工，工作区提升只生成未发布修订。Android 读取 API 仍只认 `tutorial_publications` 指针。

## 6. 为什么用整文档 PUT，而不是许多 PATCH 命令

管理网页目前通过：

```http
PUT /api/v1/admin/tutorial-drafts/{workspace_id}
```

替换整个小型工作区文档。MVP 选择它的原因：

- 状态图规模小，JSON 传输成本有限。
- 保存后数据库总是一个自洽快照。
- 不需要提前发明几十种 node/anchor/transition 编辑命令。
- 前端撤销、重做可以先在本地完成。

当文档变大、需要实时协作或精细审计时，可以演进到 JSON Patch、领域命令或事件溯源；现在引入会增加合并与迁移复杂度。

整文档 PUT 的主要风险是两个标签页互相覆盖，所以必须结合乐观锁。

## 7. 乐观锁：`expected_version`

每个工作区从 `version=1` 开始。更新请求必须发送自己读取时的版本：

```json
{
  "expected_version": 3,
  "document": {}
}
```

Repository 执行类似 SQL：

```sql
UPDATE tutorial_draft_workspaces
SET version = 4, document_json = ...
WHERE workspace_id = ... AND version = 3;
```

如果受影响行数是 0，说明工作区不存在或已经被别人更新。API 返回 `409 Conflict`，包括 expected 和 current version。网页不能偷偷重试覆盖，而应重新加载，让管理员决定保留哪一版。

这对应 JPA 的 `@Version` / `OptimisticLockException`。它叫“乐观”，因为正常情况下不长期持有数据库锁，只在提交时检测冲突。

## 8. 提升操作为什么必须是一个事务

提升工作区包含两次写入：

1. 向 `tutorial_revisions` 追加正式且不可变的修订。
2. 在工作区记录 promoted graph/revision，并让 workspace version 加一。

如果它们分成两个事务，第二步失败后会留下无法解释的修订；客户端重试还可能再生成一个修订。因此 `SqlAlchemyTutorialDraftRepository.promote()` 在同一个 Session transaction 内完成两步。

条件更新仍带 `expected_version`。如果发生竞争，整个事务回滚，包括刚追加的修订。

数据库层还使用：

- 复合外键确保 `(promoted_graph_id, promoted_revision_number)` 指向真实修订。
- CHECK 保证 graph id 和 revision number 同时为空或同时存在。
- CHECK 保证 workspace version 和 revision number 为正数。

领域校验、应用服务、Repository 条件更新、数据库约束形成多层防线，各自面对不同的错误来源。

## 9. API 调用链

所有工作区 API 都需要管理员认证：

```text
POST /api/v1/admin/tutorial-drafts
GET  /api/v1/admin/tutorial-drafts?limit=50
GET  /api/v1/admin/tutorial-drafts/{workspace_id}
PUT  /api/v1/admin/tutorial-drafts/{workspace_id}
POST /api/v1/admin/tutorial-drafts/{workspace_id}/validate
POST /api/v1/admin/tutorial-drafts/{workspace_id}/promote
```

最近工作区列表只返回摘要，不返回完整 document。网页需要继续编辑时再 GET 单个工作区，避免首页一次传输所有候选和资源引用。

典型状态码：

- `201`：创建工作区。
- `404`：workspace id 不存在。
- `409`：expected version 已过期。
- `422`：HTTP 文档格式错误，或者工作区不能提升。

## 10. Java 与 Python 对照

| Python 实现 | Java/Spring 类比 |
|---|---|
| frozen dataclass 草稿模型 | 不可变 command/value object |
| Pydantic DTO | Jackson DTO + Bean Validation |
| `TutorialDraftService` | Application `@Service` |
| Repository `Protocol` | Repository interface |
| 条件 UPDATE + rowcount | `@Version` optimistic locking |
| `with session.begin()` | `@Transactional` |
| Alembic migration | Flyway/Liquibase migration |
| composition root 显式装配 | `@Configuration` / dependency injection |

这里没有使用全自动依赖注入容器。`create_app()` 显式创建 Database、Repository、Service 并放入 FastAPI state。依赖关系更容易沿代码阅读，测试也能直接注入真实 SQLite 或替代实现。

## 11. 测试覆盖

本模块测试包括：

- local-only 采集拒绝资源与候选内容。
- AI/OCR 候选决策必须经过管理员复核。
- 重复 capture/candidate/artifact ID 被拒绝。
- 空草稿一次返回全部完整性问题。
- 完整草稿无损构造成原有 TutorialGraph。
- 部分文档创建、替换和读取。
- 最近工作区摘要不传完整 document。
- 旧版本 PUT 返回 409 和当前版本。
- 旧版本提升不会产生孤立修订。
- 提升原子生成正式 revision。
- 提升后 Android 公开列表仍为空。
- Alembic 从空库建立第二版 schema，并能降级回 base。

验证命令：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
```

## 12. 当前刻意未做的事情

- 没有上传或下载截图文件。
- 没有执行 Accessibility 解析、OCR 或 AI 推理。
- 没有 React 标注界面。
- 没有真正的管理员用户和会话，仍使用 bootstrap Bearer Token。
- 没有多人实时合并，只检测冲突。
- 没有自动发布路径。

这些不是遗漏，而是模块边界。先稳定“能存什么、谁能决定、何时成为正式修订”，再接入成本更高且隐私风险更大的文件和模型能力。

## 13. 建议你动手验证

迁移并启动服务后，在 Swagger UI 中：

1. 创建空工作区，观察 version 为 1。
2. validate，查看 `missing_graph_id`、`no_nodes` 等问题。
3. 用 PUT 保存完整 document 和 `expected_version=1`，观察 version 变成 2。
4. 再用 expected_version=1 保存，观察 409。
5. 用 expected_version=2 promote，得到 formal revision。
6. 调用公开 `GET /api/v1/tutorials`，确认列表仍为空。
7. 最后显式 publish，公开列表才出现教程。

## 14. 下一模块

管理网页不能安全地把一个共享服务端 Bearer Token 长期放在浏览器中。下一模块计划实现轻量管理员身份、登录会话、CSRF 边界和关键操作审计，再让 React 编辑器使用这些 API。

该模块可能引入密码哈希相关依赖；开始前会先说明环境与依赖选择，再进行安装。
