# 模块 41：求助候选队列

`HelpRequestQueue` 是 worker 的只读入口：只从 `received` 状态选取最早的求助，不会重放处理中、人审或完成的记录，也不在选择时改变状态。真正的 claim 仍必须与模块 36 的持久化租约结合并用 CAS 完成。
