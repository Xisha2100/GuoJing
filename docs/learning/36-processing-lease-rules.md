# 模块 36：处理租约规则

后台 worker 不能永久占有一条求助。`ProcessingLease` 是无 I/O 的值对象：它要求时区感知的时间、正的有效期；到期瞬间即可被接管；原 worker 只能在未过期时续租。

这为后续数据库 compare-and-swap claim 提供规则层，不把 SQL、线程或模型调用带入领域层。Java 中可把它理解为不可变 `record`，repository 再用 `WHERE expires_at <= now OR worker_id = :worker` 实现原子更新。
