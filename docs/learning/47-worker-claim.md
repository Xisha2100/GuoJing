# 模块 47：Worker Claim 组合

`HelpRequestWorkerClaimer` 将队列的最早候选和 `ProcessingLease` 放在同一个不可变结果中。后续数据库实现应在事务内完成同样的选择与 CAS 更新，不能把这个内存组合误当作跨进程锁。
