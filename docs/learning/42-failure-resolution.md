# 模块 42：失败处理决策

`HelpRequestFailureResolver` 将重试策略转成明确结果：`retry_after` 或 `requires_human_review`。调用者无需猜测 `None` 的含义，因此无法把到达预算的任务继续放回队列。
