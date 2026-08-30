# 模块 30：模型最小任务上下文与 deadline

## 目标

模型适配器不能只是“传一个 request ID，然后等它回来”。那既没有足够的任务约束，也无法处理永久阻塞。本模块为通用指引模型定义了明确、最小的上下文与时间边界，同时保持模型不拥有状态写入或 Android 操作能力。

## 传给模型的内容

`ModelGuidanceContext` 包含：

- 请求 ID、意图和处理路由，用于关联日志和选择正确的处理分支；
- 固定的通用任务：为不熟悉智能手机的用户提供安全、手动的基础说明；
- 三条不可省略的安全规则：仅解释可见界面、不触及支付/密码/验证码等危险操作、每一步必须让用户本人确认；
- UTC `deadline_at`，同时作为 adapter 的总时限。

它**不包含**原始问题、截图、OCR、Accessibility 节点文本、联系方式、支付数据、坐标或手势命令。当前通用路由的生产实现仍是确定性基础指引；将来若要让模型按用户自由文本定制答案，需要单独设计加密存储、最短留存、删除机制和用户授权，不能顺手把问题正文塞进当前结果表。

## timeout 为什么需要两层

`GuidanceModel.generate(context, deadline=...)` 要求真实 Deep Agent 或 HTTP adapter 把 deadline 映射为连接、读取和总超时。`SafeGuidanceModelProcessor` 还使用一个单 worker 的执行器等待同样的总时长：超时即返回 `needs_human_review`。

Python 线程不能安全地强杀一个正在执行第三方 SDK 的调用。因此 timeout 后不会假装调用已经取消：未完成调用继续占用唯一槽位，后续模型请求直接转人工复核，直到该调用真正结束。这是 fail-closed 的资源上限，而不是无限制地创建后台线程。应用退出或测试结束时可调用 `shutdown()` 取消尚未开始的任务并释放 executor 资源。

```text
HelpRequestResult（无截图、无问题正文）
  -> ModelGuidanceContext（任务 + 规则 + deadline）
  -> GuidanceModel adapter（必须传递网络 timeout）
  -> StructuredGuidanceParser
  -> HelpRequestGuidance 或 needs_human_review
```

## 与 Java 的对应关系

这相当于 Java 的 `ExecutorService` + 有界并发数 + `Future.get(timeout)`。但 Java 的 `future.cancel(true)` 和 Python 的 `future.cancel()` 都不能保证中断任意网络库，所以 provider 本身仍必须正确使用 timeout。服务端处理状态的 CAS（模块 29）会防止超时 worker 之后迟到的写入覆盖其他终态。

## 验证

测试覆盖正常模型输出、未知字段和危险指引拒绝、教程路由拒绝，以及永不返回的模型：第一次调用在 deadline 后进入人工复核，第二次因唯一槽位仍被占用也安全降级。测试不依赖 API Key、网络或真实模型供应商。
