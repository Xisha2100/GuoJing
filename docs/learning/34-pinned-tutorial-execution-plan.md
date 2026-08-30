# 模块 34：固定教程执行计划

## 问题

“找到了微信教程”还不是可执行的安全结论。若只把 `graph_id` 返回给 Android，客户端、模型，甚至未来重试的 worker 都可能读取到另一版教程，或从当前节点挑选金融、不可逆的 transition。

本模块把一次强匹配转换为不可变的 `HelpRequestTutorialPlan`：

- 教程图 ID；
- 匹配时的节点 ID；
- 已发布修订号；
- 版本兼容评估状态；
- 该节点仅限低风险的 transition ID 列表。

计划不含坐标、Accessibility 文本、截图、手势或自动执行命令。Android 仍须展示说明、等待用户亲自操作，再以页面证据验证状态。

## 调用链

`HelpRequestWorkflow` 在教程匹配器给出 `MATCHED` 后，调用 `TutorialExecutionPlanService`。服务重新读取该图的**当前已发布版本**，确认修订号仍然相同，才筛选该节点的出边。筛选复用模块 31 的 `authorize_guidance_action`：只有低风险 transition 进入计划。

随后计划与求助状态一起写入 SQLite；状态轮询接口再投影成 `tutorial_plan`。数据库使用 JSON 字符串保存一个小型、已校验的值对象，避免为五个固定字段过早建复杂的关系表。Alembic `20260830_10` 负责把列加入已有部署。

## 为什么要再次确认 revision

匹配和构造计划之间可能发生管理员发布新修订。此时“匹配到 revision 1、却执行 revision 2”会破坏可复现性。服务会直接失败并停下，让工作流走人工处理，而不是悄悄采用最新版。

## Java 对照

这相当于把一次规则计算得到的 `ExecutionPlan` 作为不可变 DTO（Java 中通常是 `record`），持久化时存 JSON，读取时重新构造并校验。`state_version` 的 compare-and-swap 仍负责防止两个 worker 相互覆盖；固定计划解决的是“写入内容是否仍是同一份安全决策”。

## 验证

- 单元测试确认金融 transition 不会进入计划；
- SQLite 重启后的读取保留完全相同的计划；
- API 工作流和轮询接口返回相同计划；
- 全量后端质量门禁通过后再提交。
