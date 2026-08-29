# 模块 17：求助处理器端口与确定性安全分支

## 1. 目标

模块 16 固定了求助结果状态，但还没有一个可以推进状态的 application use case。本模块增加 `HelpRequestProcessor` 端口和 `HelpRequestService.process()`，先用不依赖模型的实现验证生命周期。

## 2. 调用链

```text
HelpRequestService.process(request_id, processor)
  → received → processing
  → processor.process(metadata-only result)
  → needs_human_review 或 guidance_ready
```

处理器收到的对象不含图片和问题正文。图片在模块 12 的接收边界已经被丢弃，因此任何未来模型适配器都必须先设计新的、受控的证据合同，不能偷偷重新读取原图。

## 3. 为什么使用端口

`HelpRequestProcessor` 是 Python 中的 `Protocol`，作用类似 Java 的接口。application service 依赖抽象，测试可以注入确定性 fake，未来再接队列 worker、教程检索或 DeepAgent，而不用修改状态机和 HTTP 层。

`HelpRequestProcessorOutcome` 只允许两个终态：人工复核或指引可读。处理器不能返回任意状态，也不能直接改写请求对象。

## 4. 安全行为

- `recorded_tutorial` 在没有当前页面证据时进入人工复核；不猜测教程步骤。
- `general_guidance` 才能进入基础指引目录。
- 状态迁移仍由 `HelpRequestResult.transition()` 集中校验。
- 指引步骤继续经过人工操作和危险词规则检查。

## 5. 测试与学习要点

测试覆盖完整分支、终态载荷不完整、基础指引必须是人工步骤，以及 service 实际推进状态。这个模块对应 Java 后端中“application service + strategy port + immutable outcome”的组合；Python `Protocol` 只描述能力，不要求继承。

## 6. 限制

当前 `process()` 是同步调用，结果仍在进程内存中。真正的后台队列、重试和持久化属于后续生产化工作。
