# 模块 33：求助 Capability 与请求归属

## 为什么 UUID 不够

请求 UUID 难以猜测，但它不是认证。只要 UUID 泄露，其他客户端仍可能读取状态或上传伪造证据。为 MVP 建完整账户体系并不必要，因此本模块采用每次求助独立的短期 bearer capability。

## 设计

创建求助时服务端随机生成 `access_token`，只在 `202` 收据中返回一次；数据库保存有限窗口内的 SHA-256 digest 列表（兼容旧的单 digest 字段）。Android 将 token 保留在当前 `HelpRequestReceipt`，并在以下请求使用 `X-Help-Request-Token`：

- 上传 Evidence Envelope；
- 读取最新 Evidence；
- 轮询求助结果。

令牌与求助的 TTL 一起过期。无令牌或错误令牌一律返回 `404`，不泄露请求是否真实存在。管理员 API 继续采用 Session + CSRF，不混用客户端 capability。

重复提交同一 `client_request_id` 会追加一个短期重叠 capability：这让“服务端已接收但 Android 未收到响应”的重试能取得新的凭证，同时乱序返回的旧凭证仍可用；窗口上限避免摘要无限增长。

## Java 对照

它类似下载链接的 signed capability，但这里服务端存储的是不可逆摘要，而不是明文 token。和 Cookie 登录相比，它的权限范围更窄：只能操作一条、有限期的 help request。

## 验证

后端测试确认错误 token 无法读取结果或上传 evidence；Android 测试确认 sender 和 status reader 都附带 header，并对 `schema_version=1.2` fail closed。
