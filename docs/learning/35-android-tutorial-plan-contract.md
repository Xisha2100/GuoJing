# 模块 35：Android 固定计划契约

Android 的状态读取器现在解析 `tutorial_plan`，但只在 `tutorial_matched` 阶段接受它，并要求其 `graphId`、`nodeId`、`revisionNumber` 与 `tutorial_match` 完全一致。transition ID 数量限制为 20，不能为空且不能重复。

这是典型的客户端 fail-closed 协议处理：服务端新字段不是“可信命令”，而是经过本地结构校验的只读数据。它没有调用 Accessibility action、手势或支付接口；既有执行引擎仍只显示步骤并等待用户确认和页面验证。

Java 对照：这相当于 Jackson 反序列化之后，再执行一个跨字段 bean validation。单字段类型正确并不表示整份消息安全。

验证：Android JVM 测试覆盖匹配计划读取；`testDebugUnitTest` 与 `lintDebug` 通过。
