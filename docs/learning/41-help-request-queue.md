# 模块 41：求助候选队列

`HelpRequestQueue` 是 worker 的只读入口：优先从 `received` 状态选取最早的求助，并在 processing 更新时间超过租约窗口后返回 stale 项进行恢复。选择本身不改变状态；数据库级原子 claim、worker ID、attempt 和 lease 持久化仍是后续工作。
