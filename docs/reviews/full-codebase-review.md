# 全代码库问题与设计审查报告

检查日期：2026-08-31

审查基线：`ed8ecef`（`codex/android-guidance-overlay`）

检查范围：后端 `src/guojing/`、数据库模型与 Alembic 迁移、全部 Python 测试、React 管理端、Android 主代码/JVM/设备测试代码、README、模块 00–58 学习文档，以及此前模块 10–25 中期检查报告。

本报告以当前代码为准。此前中期报告中的证据时间边界、状态 CAS、结果 capability、Android 收据关联、OCR 一对一匹配等问题已经在后续模块修复，不再重复列为当前缺陷。

## 本次按报告完成的修复

本次提交已处理以下高风险项：

- 发布服务加载指定不可变修订并执行 `assess_readiness()`；Android 详情页和 ViewModel 接入本地启动闸门。
- 幂等回执改为保留有限重叠 capability 摘要，并新增数据库迁移；乱序响应中的旧 token 仍可访问。
- 队列加入 stale `processing` 恢复选择，工作流异常和等待证据超时自动转人工复核；活动请求不再被容量淘汰。
- 公开提交加入应用层 IP 窗口限流和 429 背压；容量满时只清理已完成结果，否则拒绝新请求。
- 持久化经过长度约束的问题正文供人工审核，管理端展示该上下文但仍不展示截图/OCR。
- 模型上下文传递用户问题和调用 deadline；服务端匹配开始使用上传的 normalized bounds 校验相对约束。
- Android 仅在 `SavedStateHandle` 中保存加密后的最小回执，密钥由 Android Keystore 管理，离开求助流程会清除。

仍未在本次提交中完成的结构性事项包括：跨三端教程求助发现协议/evidence sender/launch guard 的完整闭环、数据库级原子 lease/attempt/retry、Android 加密收据恢复、审计 outbox、管理端完整审核决定 UI、运行时 schema 校验、修订号并发序列化和查询级 claim。报告中这些条目仍视为未完成，不应据此宣称真实生产闭环已完成。

## 总结结论

代码库的分层、静态质量和多项隐私防线总体良好，现有自动化也全部通过。但当前最大的风险不是单个函数写错，而是大量“规则对象、适配器和单元测试已经存在，生产纵向链路却没有真正接上”。README 所称的“Android 提交 → 后端批处理 → 管理网页查看/处理 → Android 展示安全结果”的 MVP 闭环，目前只对“管理员手动触发的通用固定指引”勉强成立；录制教程求助、证据匹配、人工复核和求助计划启动均未形成可运行闭环。

本次确认 6 项高严重度问题、13 项中严重度问题。最严重的是：发布就绪规则没有接入发布入口；未验证/敏感模板可被正式发布；Android 的安全开始门禁又是未使用代码；教程求助证据发送器和启动守卫没有接入生产；worker 没有真正的 claim/lease/恢复；人工复核拿不到足够上下文；幂等重试会使先前合法的 capability 失效。

因此，当前项目更准确的状态应是：**三端基础能力和安全组件较完整，但 MVP 纵向闭环尚未完成，不宜进入真实用户或多进程部署。**

## 已确认的高严重度问题

### P1-1（已修复）：发布就绪规则未接入，未验证或非低风险教程可以公开发布

证据：

- `src/guojing/application/tutorials/readiness.py:19-27` 明确定义：存在未验证页面、非 `local_only` 页面或非低风险步骤时不得就绪。
- `src/guojing/application/tutorials/service.py:24-28` 的正式 `publish()` 只检查修订号为正，随后直接移动发布指针，完全没有读取修订图或调用 `assess_readiness()`。
- `src/guojing/application/tutorials/scenario_templates.py:88-139` 的 13 个场景模板多数为 `PROVISIONAL`，且包含 `SENSITIVE`、`FINANCIAL` 步骤；它们可以导入工作区、提升为修订，再由发布 API 公开。
- `android/.../ui/detail/TutorialSafetyPresentation.kt:12-18` 虽然计算了 `canStart = local_only && all low-risk`，但主代码没有任何调用者。
- `android/.../ui/detail/TutorialDetailScreen.kt:172-179` 的“开始查看步骤”按钮始终可用。

当前 HEAD 的最小复现结果：

```text
{'ready': False,
 'reasons': ('存在未验证页面', '存在非低风险步骤'),
 'published': 'wechat_add_friend'}
```

影响：规划中的发布安全门禁只是独立单元测试，不是生产不变量。管理员误操作即可把通用锚点、未验证页面或敏感步骤暴露给 Android；Android 端也不会在开始前再次阻断。

建议：发布服务必须在同一事务语义下加载指定不可变修订、执行结构校验和 release readiness，再移动发布指针。Android ViewModel 在进入执行前应独立调用同等安全规则，界面只负责展示阻断原因。增加“所有模板默认不能发布”和“非低风险/非本地/未验证修订返回 422”的 API 回归测试。

### P1-2：录制教程求助闭环在架构上不可达

证据：

- 服务端 `workflow.py:90-105` 会把录制教程请求改为 `processing / awaiting_evidence`，没有证据就直接返回。
- Android 虽实现 `HttpHelpRequestEvidenceSender`，但 `MainActivity.kt:41-49` 没有实例化它，`GuoJingApp.kt:76-83` 和 `ScreenshotHelpViewModel.factory()` 也没有该依赖，ViewModel 从未上传证据。
- `HelpRequestEvidenceSubmission.fromObservation()` 只能从一个已经包含 graph/node/anchors 的 `ScreenObservation` 创建证据；而截图求助 UI 在服务端选出教程前并不知道 graph/node/anchors。这形成循环依赖：服务端要先收到锚点证据才能选教程，Android 又要先知道教程节点才能生成这些锚点证据。
- 初始求助请求没有目标包名或候选教程信息，截图 OCR 结果也只用于隐私提示，没有生成教程匹配证据。
- `HelpRequestTutorialLaunchGuard` 只有单测调用；求助页仅展示 plan 数量，不能下载固定修订、执行本地守卫或进入相应教程节点。

影响：选择“查找已录制教程”的真实请求会等待一份生产客户端永远不会发送、且当前发现协议无法构造的证据。即使人工通过其他方式写入 plan，Android 也只能显示文字摘要，不能安全启动计划。

建议：先重新定义发现协议。可行方案是让用户先选择目标 APP/候选教程，Android 下载候选图后在本地生成锚点证据；或由本地受限分类器先产生 package/candidate IDs。随后把 evidence sender、状态轮询、固定 revision 下载、launch guard 和从指定 node 启动执行串成一个真实 UI 状态机。必须增加跨三端组合测试，不能再以适配器单测代替闭环。

### P1-3（部分修复）：worker 没有持久化领取、租约或崩溃恢复，任务可永久卡在 `processing`

证据：

- `HelpRequestQueue.next_received()` 只查询 `received`。
- 工作流在读取证据前先执行 `received → processing`；进程在这之后崩溃时，请求不会再次进入队列。
- `HelpRequestWorkerClaimer.claim()` 只在内存中创建 `ProcessingLease`，不更新数据库、不验证所有权，也没有被 `process-next` API 使用。
- `RetryPolicy`、`HelpRequestFailureResolver`、`ProcessingAuditEvent` 同样没有接入 worker、Repository 或 composition root。
- `POST /admin/help-requests/process-next` 在 HTTP 请求线程中同步循环执行工作流；它不是后台 worker，也没有调度器、心跳或 watchdog。
- 模块 55 文档称批处理接口“复用 claim 组合”，实际代码没有调用 `HelpRequestWorkerClaimer`。

当前 HEAD 复现：将请求标记为 `processing / awaiting_evidence` 后，`HelpRequestQueue.next_received()` 返回 `None`。

影响：API 进程终止、机器重启或未来模型/OCR 卡死都会留下不可恢复任务。多 worker 并发时，CAS 能阻止陈旧覆盖，但竞争失败会直接抛错；批处理端点没有逐项隔离，可能让整个批次失败。

建议：在数据库内原子实现 `received/retryable → processing` claim，持久化 worker ID、lease expiry、attempt、next_attempt_at 和最后错误类别；过期 lease 可安全接管。worker 应是独立进程/任务而非管理员 HTTP 长请求，批次应逐项记录结果和冲突。当前未接线的规则对象应在一个模块内完成落地，否则应删除“已完成”表述。

### P1-4（部分修复）：人工复核没有足够上下文，也没有完整的 Web 操作闭环

证据：

- `HelpRequestService.accept()` 只把问题哈希放入幂等指纹，数据库不保存问题正文；截图在校验后立即清零。
- 管理复核列表只返回 intent、route、status、时间和 review reason；没有脱敏问题、候选教程、plan 详情或可供管理员读取的安全证据。
- Web `HelpRequestPanel.tsx` 只能刷新列表和触发下一批，不能打开请求、编辑/发布人工指引、确认教程版本或标记无法处理。
- 后端虽然有 `POST /{request_id}/guidance`，但 Web 没有调用；即使直接调用 API，管理员也不知道用户具体问了什么。

影响：“转人工复核”实际上是不可处理的终态。管理员只能看到“需要复核”及泛化原因，无法形成与用户问题相关、可审计的答案。

建议：定义经过用户同意、最小化且有保留期限的复核上下文，例如脱敏问题、结构化目标、package/candidate IDs 和非原文证据摘要；为管理员提供详情、决定、发布和拒绝 UI。若隐私策略决定不保存任何上下文，就应删除“人工复核可回答”的产品承诺，把该状态改为明确的“请联系家属/重新发起”。

### P1-5（已修复）：幂等重试轮换唯一 capability，乱序响应会让客户端保存失效令牌

证据：

- `HelpRequestService.accept():95-115` 每次 POST 都生成新 token。
- SQL 和内存 Repository 在命中相同 `client_request_id + fingerprint` 时都会覆盖唯一的 `access_token_digest`。
- 若请求 A 已成功、重试 B 随后轮换到 token B，但响应 A 最后到达，客户端会保存 token A；此时状态查询和证据上传全部返回 404。
- SQL `IntegrityError` 并发分支只读取既有记录，却仍向调用方返回本次新生成、没有写入数据库的 token，存在更直接的无效收据路径。

当前 HEAD 复现：

```text
{'same_request': True, 'old_token_valid': False, 'new_token_valid': True}
```

影响：幂等机制避免了重复建单，却破坏了最常见的“服务端已接收但响应丢失”恢复场景。网络乱序或并发重试会把合法用户永久锁在自己的请求之外。

建议：同一个幂等请求应返回稳定 capability；若必须轮换，应支持旧 token 的短暂重叠、明确版本号并保证原子写入后才响应。并发唯一约束分支必须返回一个数据库中真实有效的 token。补充乱序响应、并发首次提交和跨实例重试测试。

### P1-6（已修复）：公开提交端点没有滥用防护，固定容量会删除合法活动请求

证据：

- `POST /api/v1/help-requests` 是公开端点，没有设备凭证、IP/设备频率限制、并发限制或配额。
- 中间件只限制单个请求体为 12 MiB，不限制请求数量。
- `SqlAlchemyHelpRequestRepository._evict_if_full()` 达到 1000 条后按最旧 `updated_at` 无差别删除，包括 `received`、`processing` 和 `needs_human_review`。
- Android 提交最小合法 JPEG 的成本很低，攻击者可持续创建新 client IDs。

影响：外部请求可稳定淘汰正常用户的活动任务、capability 和关联证据；这是可远程触发的数据丢失与服务降级，而不仅是容量优化问题。

建议：增加反向代理和应用层双重限流、设备安装级凭证/匿名配额、全局背压及监控。容量不足时应拒绝新请求或只清理过期/已完成结果，不能静默删除进行中任务。

## 中严重度问题与不合适设计

### P2-1（已修复）：异步求助收据只存在 ViewModel 内存中

`ScreenshotHelpUiState.Submitted` 现在通过 `SavedStateHandle` 保存加密的最小回执，密钥由 Android Keystore 管理；离开求助页仍会调用 `discard()` 清除。当前仍未提供跨多个求助单的历史列表或服务端到期时间字段，后续应补充明确的历史/删除体验。

### P2-2（部分修复）：“截图问一问”当前仍不使用截图语义

通用处理器仍返回固定安全目录，截图在校验后丢弃；但 `ModelGuidanceContext` 和 Deep Agent 适配器现在会传递经过长度约束的问题正文。若接入模型，仍需明确经过脱敏的页面语义协议，不能把原始截图直接送入模型。

### P2-3（已修复）：相对布局约束只是数据模型，匹配算法从未使用

Python 和 Android 都定义、解析并校验 `RelativeConstraint`；服务端现在会在 bounds 同时可用时重新计算相对关系，缺少 bounds 的旧客户端继续走语义匹配。后续仍可将同一规则下沉到 Android，减少端间差异。

### P2-4：人工自由文本的安全性仍依赖有限关键词黑名单

模型路径已改为 approved action IDs，这是正确方向；但管理员人工发布仍接受任意标题和说明，再靠 `_UNSAFE_GUIDANCE_TERMS` 做字符串包含判断。“把一千元打给对方”等同义表达可以绕过，而 API 注释声称发布的是 non-dangerous guidance。建议人工端同样选择结构化动作/风险分类；未知或敏感动作显式二次确认，金融和不可逆操作硬阻断。关键词只能作为附加提示。

### P2-5：教程修订号使用 `MAX + 1`，并发创建会冲突并返回 500

`tutorial_storage.py:74-79` 先查询最大修订号再加一，没有锁、重试或数据库序列。两个并发提升/保存可选择同一编号，唯一约束随后抛 `IntegrityError`；API 没有将其翻译为可恢复冲突。应使用数据库原子计数、带锁父记录或在唯一冲突后有限重试。

### P2-6：审计记录只证明“请求过”，不能证明操作结果

关键变更为避免“状态成功而审计失败”，现在先写 `*_requested` 再变更。这比无审计更安全，但失败操作也会留下 requested，成功操作没有 committed/failed 事件，管理员无法从审计表判断最终结果。批处理更只记录一个批次意图，没有逐项 outcome。应采用 transactional outbox 或至少记录可关联的 requested/completed/failed 三阶段事件及状态版本。

### P2-7（部分修复）：Deep Agent deadline 未传递，超时线程可永久占用唯一槽位

`DeepAgentGuidanceModel.generate()` 现在把绝对 deadline 传给支持该参数的新 invoker，并兼容旧的单参数适配器。外层 Future 超时后仍不能终止已阻塞的旧调用；真实适配器需要把 deadline 映射到连接/读取/总超时，并使用可终止的进程或支持取消的客户端。

### P2-8：管理员登录节流容易被用于账号锁定，认证表没有保留策略

节流只按标准化用户名统计，不含来源 IP/设备维度；攻击者知道管理员用户名后，可持续制造 15 分钟锁定。`count` 与 `record` 也不原子，并发失败可越过阈值。登录尝试、已过期/撤销 session 和审计事件没有清理或归档；每次认证还都会更新 `last_seen_at`，造成 SQLite 写放大。建议组合账号与来源限流、原子计数/退避、定期清理，以及按时间窗口节流 last-seen 写入。

### P2-9（部分修复）：教程和工作区输入缺少总量与长度边界

教程 DTO 现在为主要字符串、节点/锚点/边、captures、artifacts 和 candidates 增加长度与数量上限；帮助请求仍有 12 MiB 前置限制。管理员编辑 API 尚未增加独立请求体上限，图复杂度也仍需更细粒度预算。

### P2-10（部分修复）：TTL/容量仍是惰性清理，测试替身与 SQL 证据策略不一致

结果和证据仍只在读写时清理，低流量时数据库与备份可能超过声明 TTL；这需要独立清理任务。全局结果容量现在只清理 `guidance_ready`，若全部为活动请求则拒绝新请求。SQL evidence 的单请求限制与内存替身统一仍待补齐。

### P2-11：管理端类型安全停在编译期，运行时响应直接强制转换

`web/admin/src/api/client.ts:56-62` 将任意 JSON 直接 `as T`，没有 schema/version 运行时验证；后端协议漂移可在组件深处变成异常或错误展示。`HelpRequestPanel` 首次渲染不自动加载，却显示“当前没有”，产生假空状态；处理批次结果被声明为 `unknown[]` 并丢弃。应使用运行时 schema、显式 loading/not-loaded 状态，并展示批处理逐项结果。

### P2-12：管理端仍是原始 JSON 编辑器，不适合作为教程录制/审核工具

当前 Web 支持完整 JSON 文本编辑、校验和提升，但没有节点/边可视编辑、候选锚点审核、真实设备版本确认、就绪门禁解释或发布 UI。它适合开发调试，不适合规划中的家属/运营人员生产教程。建议保留 JSON 高级模式，同时提供结构化表单、图预览、风险标签、设备验证记录和独立发布确认。

### P2-13：队列和教程查询采用全量加载，扩展后会快速退化

队列每处理一条都 `list(received)` 全量读取再在 Python 中取最早项，批次形成重复全表扫描；教程匹配先加载全部发布摘要，再逐个 `get_published()`，形成 N+1 查询和重复 JSON 反序列化。这与未来多 worker/PostgreSQL 方向不匹配。Repository 应提供带索引的原子 `claim_next(limit)` 和按 package 一次加载当前发布修订的查询。

## 低优先级质量问题

- `TutorialSafetyPresentation` 已接入详情页启动按钮；`HelpRequestWorkerClaimer`、`HelpRequestFailureResolver`、`ProcessingAuditEvent`、`HelpRequestTutorialLaunchGuard` 等仍有单测却无完整生产调用者。测试通过不能代表能力已集成。
- README 和模块 55/58 对闭环、claim 复用、模板发布门禁的描述超过当前实现。文档应在修复前降级为“组件已具备/待集成”，避免后续开发基于错误前提继续堆模块。

## 做得较好的部分

- 后端领域/Application/Infrastructure 依赖方向总体清晰，领域层没有反向依赖 FastAPI、SQLAlchemy 或 Agent 框架。
- 求助图片有请求体上限、JPEG/尺寸/哈希校验、校验后清零、no-store 响应；状态和证据接口使用 capability 且避免泄漏资源存在性。
- 证据时间窗口、服务端 TTL、每请求 SQL 容量、`state_version` CAS 和严格 schema 已补齐。
- Android Photo Picker、内存副本、像素替换、显式发送同意、本地 OCR 隐私建议、离开页面清零等路径设计较稳健。
- Accessibility 在读取树前检查 `capture_paused` 和目标包；密码节点不提取文字；浮层不可触摸，并绑定 observation sequence、graph/node/package。
- Android 和后端都对未知枚举、schema 版本和矛盾结果 fail closed；金融/不可逆执行由本地执行引擎硬阻断。

## 验证结果

全部通过：

- `uv run pytest`：194 passed。
- `uv run ruff check .`：通过。
- `uv run ruff format --check .`：161 files already formatted。
- `uv run mypy`：通过，150 个源文件。
- `uv lock --check`：通过，45 个包解析一致。
- `pnpm --dir web/admin check`：Prettier、ESLint、TypeScript、11 项 Vitest 和生产构建全部通过。
- `./gradlew testDebugUnitTest lintDebug`：通过；Android JVM 测试结果共 100 项，0 failure/error。
- `./gradlew assembleDebug assembleDebugAndroidTest`：通过。
- `git diff --check`：通过。

未完成：`connectedDebugAndroidTest`。当前环境无法启动 ADB daemon，且没有确认可用的设备/模拟器；这不计为代码失败，但本次报告没有把 README 中既往 Pixel 7 实机结论当作当前复验结果。

## 测试体系的主要盲区

现有测试数量和单元覆盖不错，但缺少以下能发现本报告问题的集成门禁：

1. 模板导入 → 提升 → 发布必须受 readiness 阻断。
2. Android 录制教程求助 → 上传证据 → worker claim → 匹配固定修订 → Android 本地 launch guard → 从指定节点执行。
3. 并发首次提交、乱序幂等响应、token 有效性和客户端进程恢复。
4. worker 在 claim 后、状态更新后、外部调用中崩溃的 lease 接管与有限重试。
5. 管理员查看足够的脱敏上下文、发布/拒绝人工结果、审计 outcome 的完整流程。
6. 未认证提交的速率、容量、背压和活动请求不被淘汰。
7. 真实设备上的页面观察、浮层隐藏、截图生命周期和进程死亡恢复。

## 建议修复顺序

1. 立即关闭未就绪修订发布路径，并把 Android 开始门禁接入 ViewModel/UI。
2. 重新设计录制教程的候选发现与证据协议，完成 evidence sender 和 launch guard 的生产集成。
3. 实现数据库原子 claim、lease、attempt、retry/watchdog 和独立 worker；停止把同步管理 API 当生产队列。
4. 修复 capability 幂等语义，并为 Android 持久化最小加密收据。
5. 明确人工复核所需的最小脱敏上下文，补齐管理详情、决定、发布与拒绝界面。
6. 增加公开端点限流、背压、状态感知容量和独立 TTL 清理。
7. 再处理修订并发、审计 outbox、输入规模、运行时协议校验和查询性能。

完成前 6 项并新增对应端到端测试后，才建议恢复 README 的“最小闭环已完成”结论。
