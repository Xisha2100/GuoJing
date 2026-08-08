# 模块 05：管理端身份认证与安全审计

本模块把之前仅用于后端联调的共享 Bearer Token，替换为适合浏览器管理网页使用的轻量管理员账号、服务端会话、CSRF 防护和审计记录。

它解决的是“谁可以编辑和发布教程”，并不等同于面向老人或家属的完整账号系统。当前 MVP 仍然只有管理员角色，没有注册、找回密码、MFA 和复杂权限模型。

## 1. 本模块的边界

完成的能力：

- CLI 交互式创建管理员和重置密码。
- Argon2id 密码哈希及参数升级能力。
- 登录、查询当前身份和退出 API。
- 服务器保存的不透明会话，支持固定过期与撤销。
- HttpOnly、SameSite 和可配置 Secure Cookie。
- 双提交 Cookie 模式的 CSRF 校验。
- 基于用户名和时间窗口的持久化登录节流。
- 登录、退出、密码重置和教程管理请求的审计事件。

有意没有实现：

- 家属自助注册和账号恢复。
- 邮件、短信验证码或 MFA。
- OAuth/OIDC 和第三方身份提供商。
- RBAC/ABAC 等多角色权限模型。
- 跨设备会话管理页面。
- 反向代理后的 IP 级限流。

这是 YAGNI 的应用：先为下一个 React 管理网页提供可靠的身份边界，不提前制造完整 IAM 平台。

## 2. 分层与调用链

```text
浏览器
  │ Cookie + X-CSRF-Token
  ▼
FastAPI auth/dependency 适配器
  │
  ▼
AdminAuthService（应用用例）
  ├── PasswordHasher Protocol
  └── AdminAuthRepository Protocol
          │
          ▼
SQLAlchemy + SQLite
```

- `domain/auth.py`：用户名、密码策略、管理员和已认证会话值对象。
- `application/auth/`：登录、鉴权、CSRF、重置密码等用例及端口。
- `infrastructure/security/passwords.py`：Argon2id 适配器。
- `infrastructure/persistence/admin_auth_repository.py`：账号、会话、尝试和审计持久化。
- `api/admin_auth.py`：HTTP JSON、Cookie 和状态码转换。
- `api/dependencies.py`：为管理路由集中执行会话与 CSRF 校验。
- `cli.py`：不经过 HTTP 的运维入口。

依赖继续向内：应用层知道“需要密码哈希器”，但不知道 argon2-cffi；领域层也不知道 FastAPI、Cookie 或 SQLAlchemy。

Java 对照：

- `PasswordHasher Protocol` 类似自定义的 `PasswordEncoder` 接口。
- `AdminAuthService` 类似 Spring application service。
- FastAPI dependency 类似 Spring Security filter/interceptor 后生成的认证上下文。
- SQLAlchemy repository 类似基于 JPA 的 repository adapter。
- Pydantic `Settings` 类似带校验的 `@ConfigurationProperties`。

## 3. 密码为什么使用 Argon2id

密码具有两个危险特征：用户通常记得住，因此熵较低；同一密码还可能被多人重复使用。攻击者获得数据库后，可以离线高速猜测常见密码。

普通 SHA-256 的设计目标是快。对于文件校验很好，但用于密码会让攻击者每秒尝试海量候选。Argon2id 是自适应、带盐、内存困难的密码哈希算法：

1. 每次哈希自动生成随机 salt，相同密码不会得到相同编码值。
2. 计算故意消耗时间和内存，提高批量猜测成本。
3. 编码字符串同时保存算法、参数、salt 和结果，以后可以识别旧参数。
4. 成功登录时调用 `check_needs_rehash`，参数升级后可透明生成新哈希。

代码没有自行拼装盐值或算法参数，而是使用 `argon2-cffi` 的高层 `PasswordHasher`。自行设计密码学格式几乎总是增加风险。

### 为什么测试不用真实 Argon2

安全算法的计算昂贵是功能，不是性能缺陷。但大部分单元和 HTTP 测试只需要验证端口契约，不需要反复证明 Argon2 本身有效，因此注入快速的测试哈希器。另有独立适配器测试验证真实 Argon2：

- 相同密码的两个哈希不同。
- 正确密码验证成功。
- 错误密码验证失败。
- 编码值使用 Argon2id。

这和 Java 项目中在 service test 里 mock `PasswordEncoder`，再对 BCrypt/Argon2 adapter 做少量集成测试相同。

## 4. 密码哈希与会话令牌摘要为什么不同

数据库中的密码和会话令牌都不保存明文，但使用了不同算法：

| 数据 | 原始熵 | 数据库形式 | 算法选择 |
|---|---:|---|---|
| 用户密码 | 通常较低 | Argon2id 编码哈希 | 必须昂贵，抵抗离线猜测 |
| 会话/CSRF 令牌 | 服务器随机生成，至少 32 字符 | 64 位十六进制摘要 | SHA-256 足够，原值不可猜 |

会话令牌来自密码学安全随机数生成器，攻击者无法构造一个小型常用词字典去猜它。此时数据库只需要像保存 API key 一样保存快速、不可逆的 SHA-256 摘要。每次请求把 Cookie 原值做摘要后查询，数据库泄漏不会立即泄漏仍可使用的原始令牌。

不要把这个结论反过来套到用户密码上。

## 5. 为什么选择服务端不透明会话，而不是 JWT

浏览器 Cookie 中保存的是无业务含义的随机字符串；用户、有效期、撤销状态和 CSRF 摘要都位于 `admin_sessions` 表。

对于当前小型管理端，这比 JWT 更合适：

- 退出登录可以立刻撤销数据库记录。
- 重置密码可以一次撤销该账号的全部会话。
- 停用账号后，旧会话不再有效。
- 不需要管理 JWT 签名密钥、轮换和 token denylist。
- 每次请求本来就需要访问本地 SQLite，JWT 的无状态优势没有实际价值。

代价是每个认证请求多一次数据库查询。当前管理端流量很低，这个取舍清晰且可接受。

会话采用固定过期时间：`expires_at = created_at + TTL`。访问只更新 `last_seen_at`，不会自动延长有效期。这样最长存活时间容易推理，也避免被长期使用的已窃取 Cookie 无限续期。

## 6. Cookie 安全属性

登录成功设置两个 Cookie：

### 会话 Cookie

- `HttpOnly=true`：浏览器 JavaScript 不能读取，降低 XSS 直接窃取会话的能力。
- `SameSite=Strict`：跨站请求默认不携带。
- `Path=/api/v1/admin`：只发送到管理 API。
- `Secure=true`：staging/production 强制，只经 HTTPS 发送。

### CSRF Cookie

`HttpOnly=false`，因为 React 需要读取它并复制到 `X-CSRF-Token` 请求头。它使用 `Path=/`：管理网页和 `/api/v1/admin` API 没有更窄的共同路径，如果也限制为 API Path，位于 `/admin` 的页面脚本将无法读取。Cookie Path 不是权限边界，真正的防护来自随机值与服务端会话摘要的绑定。

本地开发通常是 `http://127.0.0.1`，所以允许 `Secure=false`。这不是生产安全选项：配置模型明确拒绝 staging/production 使用不安全 Cookie。

`HttpOnly` 不是 XSS 万能药。恶意脚本虽然读不到会话 Cookie，仍可能借当前页面发请求，因此还需要输入输出安全、CSP 等前端防线。

## 7. CSRF：为什么 Cookie 还需要第二个令牌

浏览器会自动附带 Cookie。攻击者可以诱导已登录管理员访问恶意网站，由恶意页面向本系统提交请求；即使攻击者看不到响应，写操作也可能发生。这就是 CSRF。

本模块使用双提交 Cookie模式：

1. 登录时生成独立随机 CSRF 令牌。
2. 浏览器保存可读的 CSRF Cookie。
3. React 把这个值复制到 `X-CSRF-Token` 请求头。
4. 后端先比较 Cookie 与 Header，再比较它们的 SHA-256 与会话表中的摘要。

跨站 HTML 表单可以发 Cookie，但不能任意添加自定义 Header，也读不到目标站点的 Cookie，因此无法完成三者匹配。

所有状态变更管理 API 使用 `require_admin`，同时检查会话和 CSRF；只读 GET 使用 `require_admin_session`。集中依赖可避免某个路由忘记校验。

## 8. 登录枚举与暴力尝试

### 统一错误

用户名不存在、密码错误、账号停用都返回相同的 `401 invalid username or password`，避免直接告诉攻击者哪些用户名存在。

### dummy hash

如果用户名不存在，服务仍然验证一次启动时生成的 dummy Argon2 hash。否则“不存在”路径不做昂贵哈希，响应时间可能明显更短，攻击者可据此推测账号是否存在。

这只能缩小时间差，不能承诺互联网环境下绝对恒定时间。

### 持久化节流

失败尝试记录在数据库，而不是只放内存：

- API 重启不会清空计数。
- 多 worker 在共享数据库时看到相同状态。
- 成功登录后，之前的失败不继续惩罚该用户。
- 默认 15 分钟内 5 次失败，之后返回 `429` 和 `Retry-After`。

当前只按规范化用户名节流。未来部署到互联网时还应在可信反向代理或网关加入 IP/设备级限流；直接相信客户端传入的 `X-Forwarded-For` 会被伪造。

## 9. CLI 为什么交互式读取密码

创建管理员：

```bash
uv run python -m guojing.cli create-admin --username admin
```

重置密码：

```bash
uv run python -m guojing.cli reset-admin-password --username admin
```

密码不允许通过 `--password` 传入，因为命令行参数可能出现在：

- shell history；
- `ps` 等进程列表；
- 终端录屏或 CI 日志。

`getpass` 不回显输入，并要求输入两次。重置密码时，更新哈希、撤销全部会话和写入审计在同一数据库事务中完成：不会出现密码已变但旧会话仍有效的部分成功状态。

CLI 不自动执行迁移。运维顺序必须是先 `alembic upgrade head`，再创建账号。结构变更与业务数据初始化保持两个明确步骤，部署失败时更容易定位。

## 10. 数据表设计

### `admin_users`

保存规范化用户名、Argon2 编码哈希、启用状态和时间戳。用户名有唯一约束，应用层的预检查不能替代数据库约束，因为并发请求仍可能同时通过预检查。

### `admin_sessions`

保存会话摘要、CSRF 摘要、创建/访问/过期/撤销时间。会话摘要唯一，且数据库检查 `expires_at > created_at`。

### `admin_login_attempts`

保存规范化用户名、是否成功和时间，用于跨重启节流。复合索引支持按用户名和时间窗口查询。

### `admin_audit_events`

保存操作者、动作、资源和非敏感 JSON 详情。密码、Cookie、CSRF 和原始截图等秘密不进入审计。

账号创建和密码重置是 CLI/系统动作，因此允许 `admin_user_id = NULL`；用户将来被删除时外键也使用 `SET NULL`，历史事件仍然保留。

## 11. 审计语义

记录的动作名称描述事实或请求，例如：

- `admin.created_by_cli`
- `admin.login`
- `admin.logout`
- `admin.password_reset_by_cli`
- `tutorial_workspace.promote_requested`
- `tutorial_revision.publish_requested`

登录、退出和密码重置的状态变化与对应审计记录处于同一 repository 事务中。教程动作当前记录为 `*_requested`，因为教程 repository 与审计 repository 还没有共享应用层 Unit of Work；它表示“哪个管理员发起了请求”，不能被误读成“业务提交一定成功”。

这是刻意准确的事件命名。未来若要审计“已成功发布”，应引入同一事务的 Unit of Work 或可靠 outbox，而不是在两个独立事务之间假装原子性。

## 12. HTTP 状态语义

- `401`：未登录、会话无效/过期、账号密码错误。
- `403`：已经有会话语境，但 CSRF 校验失败。
- `429`：登录失败次数超过窗口限制。
- `204`：退出成功且无响应体。

`401` 与 `403` 的区别对前端很重要：前者应跳转登录页，后者通常意味着前端没有正确附加 CSRF Header 或页面状态异常。

## 13. 测试策略

测试覆盖了：

- 用户名规范化与密码长度边界。
- 真实 Argon2id 的盐、验证和错误路径。
- 登录 Cookie 的 Path、HttpOnly、SameSite 与 Secure。
- 数据库不保存原始会话/CSRF 令牌。
- 错误密码与未知用户名响应一致。
- 失败节流和 `Retry-After`。
- 固定时间到点失效。
- 退出立即撤销。
- 重置密码撤销旧会话、旧密码失效、新密码生效。
- CSRF Cookie/Header 不一致返回 403。
- 教程管理请求带操作者审计。
- CLI 交互读取密码且数据库不出现明文。
- Alembic 从空库升级到 head 再降到 base。

可变时钟和 token factory 都通过构造器注入，让时间与随机性变得确定。比在测试中 `sleep` 或 patch 全局时间更快、更稳定。

## 14. 已知限制与后续方向

- 管理端尚无 React 页面，当前可通过 API 测试登录。
- SQLite 适合单机 MVP；多实例部署前需要 PostgreSQL 或共享会话存储。
- 无 MFA、账号恢复、密码泄漏字典检查和管理员停用 CLI。
- 登录节流没有自动清理历史记录，需要后续保留策略。
- 没有会话列表与“退出其他设备”。
- 审计事件不可篡改性尚未加强，拥有数据库写权限的人仍可修改记录。
- HTTPS/TLS 由未来部署入口终止，应用只强制生产 Cookie 配置。
- 前端还需 CSP、依赖供应链检查和安全输出编码。

下一个 React 管理网页模块会实际消费登录 Cookie 和 CSRF 契约。那时应把 API 调用集中到一个 TypeScript client 中，避免每个按钮手动复制安全逻辑。

## 15. 推荐继续思考的问题

1. 如果改成 JWT，如何做到“重置密码立即让全部旧 token 失效”？
2. 为什么 HttpOnly 能降低令牌被读取的风险，却不能完全阻止 XSS 发起写请求？
3. `SameSite=Strict` 已经存在，为什么仍保留 CSRF token？
4. 若教程发布和审计必须严格原子，应用层 Unit of Work 应包含哪些 repository？
5. 若从 SQLite 迁移 PostgreSQL，登录节流查询和会话唯一约束需要怎样保持语义不变？
