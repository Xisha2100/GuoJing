# 模块 21–25 中期代码检查报告

检查日期：2026-08-30

检查范围：模块 21–25 的规划与学习文档、求助结果/证据持久化、TTL 与容量控制、教程选择、求助工作流、模型适配器、安全降级，以及相关 API、Python/Android 测试和生产 composition root。

审查基线：模块提交 `4e4336a`、`e20ebf2`、`3484ef1`、`49cc695`、`417caed`。审查期间工作区另有一组模块 10–20 安全修复在并行进行；本报告没有修改这些文件，也没有把其未完成状态归因于模块 21–25。

## 结论

模块 21–25 的分层方向基本正确：领域对象不依赖 SQLAlchemy；截图、OCR 原文和 Accessibility 节点树没有进入持久化证据；教程选择复用了确定性匹配；模型输出经过结构和领域对象校验。

但“模块 21–25 已完成”的 README 结论与实际生产状态严重不符。当前存在 5 个高严重度问题和 5 个中严重度问题：模块 23–25 没有装配到生产应用，教程求助链路实际上无法运行；客户端可以把证据有效期设置到 2100 年并长期占据 latest；SQL Repository 允许旧 worker 覆盖新终态；模型拿不到用户问题或页面语义；自由文本危险词黑名单可被简单同义表达绕过。

在修复 P1 问题前，模块 21–25 应视为“完成了若干离线原型和持久化基础”，不能视为已经形成可部署的求助处理闭环。

## 模块符合度

| 模块 | 结论 | 主要原因 |
| --- | --- | --- |
| 21：求助结果持久化与 TTL | 部分符合 | SQLite Repository、跨实例幂等和访问时 TTL 已实现；状态保存没有乐观锁，旧 worker 可以回退终态，TTL 也只是惰性删除。 |
| 22：受控证据 Envelope | 部分符合 | 严格 DTO、无原文字段和 `local_only` 拒绝正确；时间与 TTL 完全由客户端决定，缺少单请求容量和真实请求归属校验，Android 也没有证据发送实现。 |
| 23：教程检索与版本匹配 | 仅离线组件符合 | 确定性匹配与稳定决策已实现，但未进入生产 composition root；低风险跨版本试运行语义没有真正接入。 |
| 24：求助编排骨架 | 不符合“已完成链路” | 工作流只在单元测试中构造；`tutorial_matched` 不是持久化检查点，结果仍停在 `processing`，也没有后续发布路径。 |
| 25：模型适配器与安全降级 | 不符合可用/安全收口 | 未装配；模型上下文不包含问题或证据，没有真正的超时；危险自由文本仍可绕过有限词表。 |

## 高严重度问题

### P1-1：模块 23–25 全部是未装配的死代码，生产 API 仍停留在模块 18

证据：

- `src/guojing/main.py:38-107` 只创建 `HelpRequestService` 和 `HelpRequestEvidenceService`，没有创建或保存 `TutorialMatchService`、`HelpRequestWorkflow` 或 `SafeGuidanceModelProcessor`。
- `src/guojing/api/help_request_review.py:107-117` 的生产处理入口仍固定调用 `DeterministicHelpRequestProcessor()`；录制教程请求会按模块 18 的旧逻辑直接进入人工复核，不读取模块 22 已上传的证据。
- `HelpRequestWorkflow`、`TutorialMatchService` 和 `SafeGuidanceModelProcessor` 的调用方仅存在于其自身模块和测试中，API/worker 没有入口。
- Android 主代码中不存在 `EvidenceEnvelope`/`HelpRequestEvidenceRequest`/`sanitized_network_allowed` 的 DTO 或发送器，学习文档所画的 `Android OcrObservationBuilder -> Evidence API` 调用链没有实现。
- 即使在单元工作流中匹配成功，`workflow.py:94-101` 只返回内存态 `TUTORIAL_MATCHED`；持久化 `HelpRequestResult` 仍是 `processing`，客户端轮询看不到匹配结果，也没有后续路径把它变成受控指引。

影响：用户可以提交截图和证据，但生产系统永远不会调用模块 23 的教程匹配或模块 24/25 的编排/模型边界。README 的“持久化结果 → 受控证据 → 教程匹配 → 编排状态 → 模型候选校验”只在几个互不完整的单元测试中成立，不是端到端功能。

建议：在 composition root 中显式注入 matcher、workflow、processor 和持久化 checkpoint；提供受认证的 worker 或处理入口；为教程匹配成功定义可轮询的持久化状态及后续安全说明路径；补齐 Android 证据 DTO/发送同意状态。新增真实 API 级回归：提交求助 → 上传证据 → 运行工作流 → 重启服务 → 轮询得到确定终态。

### P1-2：证据时间由客户端完全控制，可以绕过短 TTL 并永久污染 latest

证据：

- `src/guojing/domain/evidence.py:91-114` 只要求 `expires_at > captured_at` 且提交时尚未过期，没有限制 `captured_at` 不能在未来，也没有最大时钟偏差或最大 TTL。
- `src/guojing/application/help_requests/evidence_dto.py:69-85` 接受客户端提供的两个时间戳，没有服务端覆盖或收窄。
- `src/guojing/infrastructure/persistence/help_request_evidence_repository.py:41-49` 按客户端提供的 `captured_at DESC` 选择 latest，并按客户端提供的 `expires_at` 清理。
- `HelpRequestEvidenceService.get_latest()` 不重新检查父求助结果是否仍有效。

最小复现：在服务端时间为 2026-08-30 时，构造 `captured_at=2099-01-01`、`expires_at=2100-01-01` 的 `sanitized_network_allowed` Envelope，`require_network_allowed()` 正常通过：

```text
future_evidence_accepted = true
expires_at = 2100-01-01T00:00:00+00:00
```

影响：一次伪造或设备时钟异常即可让旧/错误页面证据在 74 年内一直压过正常证据，破坏教程选择；证据的物理保留期也不再是文档所称的短 TTL。父结果过期但尚未触发惰性清理时，latest 端点仍可返回该证据。

建议：服务端生成 `received_at` 和实际 `expires_at`；仅允许 `captured_at` 在有限过去窗口和很小的未来偏差内；把 TTL 截断为服务端配置的最大值。latest 应按服务端接收序列/时间选择，并在读取时确认父求助仍有效。`evidence_id` 应不可变，重试需校验指纹而不是覆盖内容。

### P1-3：SQL 状态保存没有 compare-and-swap，旧 worker 能覆盖新终态并让时间倒退

证据：

- `HelpRequestService._transition()` 先 `get()`、在内存中验证状态、再调用 `save()`，读取和写入不是同一事务。
- `src/guojing/infrastructure/persistence/help_request_repository.py:87-96` 的 `save()` 只按 `request_id` 查找并无条件覆盖状态、`updated_at`、指引和复核原因；没有 expected status、版本号或更新时间条件。
- 模块 21 的目标正是支持多个 Uvicorn worker，但 Repository 合同没有并发冲突结果。

最小复现：两个 worker 都从同一个 `processing` 快照产生结果。先保存较新的 `guidance_ready(updated_at=00:00:02)`，再保存旧 worker 的 `needs_human_review(updated_at=00:00:01)`，最终数据库内容为：

```text
stale_write_final_status = needs_human_review
updated_at = 2026-08-30T00:00:01+00:00
```

影响：领域层的“只允许前进”约束可被并发写绕过。已发布指引可能消失，人工复核结果也可能被另一 worker 覆盖；客户端观察到状态和更新时间倒退。工作流重试、管理员处理和未来模型 worker 都会放大此问题。

建议：为记录增加单调版本号，并使用 `UPDATE ... WHERE request_id=? AND version=? AND processing_status=?`；更新行数为 0 时返回明确并发冲突并重新读取。worker 领取任务也应原子地从 `received` claim 到 `processing`，终态写入需要幂等 key。内存 Repository 应实现同一冲突合同和并发测试。

### P1-4：模型上下文没有用户问题或受控页面语义，无法生成与请求相关的指引

证据：

- `src/guojing/application/help_requests/model_adapter.py:22-35` 的 `ModelGuidanceContext` 只有 `request_id`、`intent`、`processing_route`。
- 原始 `question` 只在接收时参与 SHA-256 指纹，`HelpRequestResult` 和数据库都不保存正文；图片在校验后擦除。
- 模型端口按设计不持有 Repository；上下文也没有模块 22 的锚点、模块 23 的 graph/node/transition ID 或已审核指令目录。

影响：真实模型无法知道用户问了什么、当前是什么页面、匹配了哪个教程节点。它只能输出与任务无关的通用模板，或根据 UUID 猜测。结构化 JSON 校验只能保证形状，不能让答案变得相关或正确。

建议：先定义最小、可证明脱敏且真正完成任务所需的上下文。通用求助若不能安全保留问题，应明确只返回静态目录而不调用模型；教程路径应只向模型提供已确定匹配的 graph/node/允许 transition，以及来自审核目录的语义，不传原图/OCR 原文。为每条输出验证它引用的允许对象，而不是只校验自由文本形状。

### P1-5：金融与不可逆安全仍依赖有限词表，简单改写即可发布危险指引

证据：

- `StructuredGuidanceParser` 只校验字段、长度和 `requires_manual_action is True`，随后依赖 `HelpRequestGuidanceStep` 的词表检查。
- 当前工作树虽已增加 Unicode 规范化和若干词项，但安全判定仍是有限字符串包含关系，没有绑定教程 transition 的 `RiskLevel` 或允许动作。

当前实现接受以下模型输出为 `guidance_ready` 候选：

```text
请把一千元打给对方。
请向对方发送一千元。
Please send $1000 to the recipient.
请解绑银行卡后继续。
```

影响：老年用户仍可能按照“必须亲自操作”的说明完成转钱、解绑银行卡或其他不可逆动作。`requires_manual_action=true` 只禁止自动点击，不等于内容安全。该问题当前因 P1-1 尚未暴露到生产模型路径，但属于接入真实模型前的硬阻断项。

建议：不要让自由文本黑名单承担金融/不可逆授权。模型只能引用经过审核的 action/transition ID，服务端按领域 `RiskLevel` 决定允许、阻止或转人工；未知动作和无法映射的自由文本一律复核。多语言归一化、金额/账号模式和安全分类器只能作为附加防线，不能替代允许列表和领域风险状态。

## 中严重度问题

### P2-1：所谓 workflow checkpoint 没有持久化，教程匹配状态可在重跑时漂移

`HelpRequestWorkflowState` 只是一次调用返回的冻结 dataclass。`AWAITING_EVIDENCE` 依靠数据库中的 `processing` 间接恢复，`TUTORIAL_MATCHED`、候选 revision 和 decision 均未写入数据库。服务重启或教程重新发布后重跑会重新计算并可能选择不同节点；客户端也只能看到永久 `processing`。应持久化 workflow stage、输入 evidence ID、教程 revision、候选 node 和状态版本。

### P2-2：模块 23 没有实现文档所述的低风险跨版本试运行

`matcher.py:134-144` 调用 `assess_node_reuse()` 时从不传入 `TutorialTransition` 或 `expected_next_state_match`。因此 APP 版本变化时，即使节点存在低风险 transition，也会走 `transition is None` 分支并返回 `TERMINAL_NODE_VERSION_CHANGED`，不可能进入文档描述的 provisional 尝试与下一状态确认。当前行为偏保守而非直接越权，但规划与实现不一致。

### P2-3：证据 API 没有请求归属证明，也没有 README 声称的单请求容量上限

`HelpRequestEvidenceService.record()` 的注释写“validate request ownership”，实际只检查 URL ID 对应的求助是否存在；POST/GET evidence 端点没有设备、会话或一次性 capability 校验。Repository 只有全局 `max_envelopes=1000`，同一个 request 可以占满全部容量并淘汰其他请求的证据。应为提交者绑定不可猜但可撤销的上传 capability/会话，增加单请求条数和频率上限，并让覆盖重试保持不可变幂等。

### P2-4：结果 TTL 和容量策略会造成超期物理保留或未完成任务丢失

结果与证据只在创建/读取/列表时惰性清理；系统停止流量后，数据库和备份中的记录可超过 TTL 长期存在。达到容量时又无差别按最旧 `updated_at` 淘汰，包括 `processing` 或 `needs_human_review` 的未完成任务。应增加独立清理任务和可监控的删除指标；容量策略应优先清理已过期/已完成记录，对进行中和待复核记录使用背压或显式归档策略。

### P2-5：文档承诺的模型超时降级没有实现

`GuidanceModel.generate()` 是无 deadline 参数的同步调用，`SafeGuidanceModelProcessor` 只用 `try/except` 捕获已经抛出的异常；调用永久阻塞时不会产生异常，也不会进入 `needs_human_review`。`HelpRequestService.process()` 又会在调用模型前把结果标成 `processing`，当前没有 lease、watchdog 或超时恢复任务。真实适配器应设置连接/读取/总时限，工作流层还要有独立 deadline 和可回收 processing lease，测试需用永不返回/超时桩确认请求最终可恢复。

## 验证结果

在隔离的已提交 HEAD 快照上：

- Python：145 tests passed。
- `ruff check`：通过。
- `mypy`：通过（113 个源文件）。
- `uv lock --check`：通过。
- `ruff format --check`：未通过，仅 `migrations/versions/20260830_04_create_help_request_results.py` 需要格式化。

当前共享工作树另有模块 10–20 安全修复正在进行，验证时得到 147 passed、3 failed，Ruff 3 项、mypy 8 项；失败均指向该并行修改的错误响应/测试类型收口，不属于模块 21–25 的已提交回归。本报告没有改动这些文件。

Android 验证：

- `./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest`：BUILD SUCCESSFUL。
- Android JVM：84 tests，0 failures，0 errors。
- `git diff --check`：通过。

现有自动化没有覆盖生产 composition root 的 21→25 全链路、未来时间戳、最大 TTL、证据请求归属、单请求容量、并发 stale write、真正持久化的 workflow checkpoint、模型超时、任务相关性和危险语义改写。这些路径应成为修复后的强制回归门槛。
