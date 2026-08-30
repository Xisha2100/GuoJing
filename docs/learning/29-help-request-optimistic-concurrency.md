# 模块 29：求助结果的乐观并发控制

## 问题

一个求助可以被管理员重试、后台 worker 重放，或在网络超时后被重复执行。若两个 worker 都读到 `processing`，先完成者写入“人工复核”后，后完成的旧 worker 仍可能把它改成“指引已就绪”。这不是简单的“后写覆盖前写”问题：它会让已经选择的安全终态丢失。

## 方案

`HelpRequestResult` 新增从 `1` 开始的 `state_version`。每次合法 `transition` 都只增加 1。Repository 的 `save` 现在接收读取快照的 `expected_version`：

```text
读取 result(version=1)
  -> 计算 transition(version=2)
  -> UPDATE ... WHERE request_id=? AND state_version=1
```

SQL 的条件更新影响行数不是 1 时，抛出 `HelpRequestStateConflictError`。内存 Repository 执行同样的版本比较，因此单元测试和生产持久化遵守同一协议。迁移 `20260830_08_add_help_request_state_version` 会把存量记录初始化为版本 1。

`HelpRequestService.process` 还缩小了异常边界：只把“处理器本身失败”转成人工复核。状态落库发生并发冲突时，不再被笼统捕获后再次写入，错误会回到 API 的 `409 Conflict` 路径。

## 与 Java 的对应关系

这就是 JPA/Hibernate 的 `@Version` 思路，只是这里使用显式的 SQL 条件：

```java
update help_request_results
set state_version = :next
where request_id = :id and state_version = :expected;
```

若更新行数为零，调用方必须重新读取，而不能盲目重试旧对象。本项目选择让管理员或队列 worker 重新检查状态；因为“把旧建议重算后再提交”在支付、社交等高风险场景可能改变安全结论。

## 验证与限制

测试构造两个 SQL 快照：第一个更新成功，第二个携带相同旧版本的更新被拒绝，并确认数据库保留第一个状态。领域测试还验证每次状态迁移递增版本。

CAS 只能阻止状态覆盖，不能把管理审计表与求助状态表变成同一个原子事务。模块 27 已把审计意图先写入；未来如果需要“操作完成”审计，应使用 outbox 或同一事务，而不是借由重试掩盖不一致。
