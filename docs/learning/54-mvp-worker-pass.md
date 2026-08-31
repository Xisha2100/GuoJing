# 模块 54：MVP Worker 单次处理

`HelpRequestWorker.run_once()` 是最小可运行 worker：每次最多处理 100 条，反复从 `received` 队列取最早请求，调用已经装配好的工作流。它不自行修改状态、不 sleep、不接触截图。

生产调度可以用 cron、launchd 或后续队列替换；处理语义留在工作流和 repository 中，便于从单进程 MVP 演进到多 worker。
