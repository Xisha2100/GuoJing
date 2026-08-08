# 模块 06：React 管理网页 MVP

本模块第一次让浏览器真正消费前五个后端模块：管理员可以登录、恢复会话、查看和创建教程工作区、编辑完整文档、保存、校验并提升为正式修订。

第一版使用完整 JSON 编辑器，而不是立即实现节点拖拽画布。它的目标是先验证认证、CSRF、工作区版本、错误语义和生产构建这条垂直链路。复杂可视化编辑器之后可以建立在一条已经稳定的 API 通路上。

## 1. 环境与版本边界

本模块使用：

- Node.js 24.18.0（项目最低要求 22.12）。
- Corepack 0.35.0。
- pnpm 11.7.0。
- React 19.2。
- TypeScript 6.0。
- Vite 8.2。
- Vitest 4.1、React Testing Library、ESLint 10 和 Prettier 3。

这些构建工具都是 `web/admin` 的项目局部开发依赖，不需要 `npm install -g`。`package.json` 声明可接受版本范围，`pnpm-lock.yaml` 固定实际解析结果。

### Corepack、pnpm 与共享存储

Corepack 负责选择项目声明的包管理器版本，角色接近“包管理器的版本启动器”。`packageManager: pnpm@11.7.0` 能减少不同开发机器使用不同 pnpm 主版本的差异。

pnpm 不会为每个项目复制一套完全独立的依赖内容。包文件进入用户级内容寻址存储，项目 `node_modules` 主要通过链接组织，因此多个项目使用同一版本时能复用磁盘内容。每个项目仍有自己的依赖图和 lockfile，不会因为共享存储而产生运行时串包。

Java 对照：

- pnpm store 类似 Maven/Gradle 的本地 artifact cache。
- `package.json` 类似 `build.gradle` 中的依赖声明。
- `pnpm-lock.yaml` 类似锁定解析后完整依赖图的版本目录；它比只声明范围更强调可复现。
- `pnpm --dir web/admin ...` 类似明确指定子模块执行 Gradle task。

### 一次真实的 peer dependency 冲突

首次安装 `typescript` 得到 7.0.2，但 `typescript-eslint 8.66` 声明支持范围为 `>=4.8.4 <6.1.0`。虽然 pnpm 可以把文件下载下来，继续使用会让 ESLint 的 TypeScript 语法树处于未受支持组合。

最终把 TypeScript 限定在 `^6.0.0`，解析为 6.0.3，并运行 `pnpm peers check` 确认没有 peer dependency 问题。

这与 Maven 插件只支持特定 JDK/编译器范围相同：安装成功不代表组合得到上游支持，peer warning 不能不加判断地忽略。

## 2. 前端目录与职责

```text
web/admin/
├── src/
│   ├── api/          # HTTP、Cookie、CSRF、响应类型和错误
│   ├── auth/         # 登录表单
│   ├── workspaces/   # 列表、JSON 编辑、校验和提升
│   ├── test/         # 测试初始化和固定样例
│   ├── App.tsx       # 会话状态与应用壳
│   └── main.tsx      # React 挂载入口
├── public/           # 直接复制的静态资源
├── vite.config.ts
├── eslint.config.js
├── package.json
└── pnpm-lock.yaml
```

当前规模不需要 Redux、Zustand 或大型组件库。认证状态只有 `checking | anonymous | authenticated` 三种，工作区状态只在对应 feature 内部使用，React 本地 state 足够清楚。

避免过早引入全局状态的原因与后端避免创建没有用例支撑的基础设施相同：抽象应该来自真实重复，而不是猜测未来。

## 3. Vite 在这里做什么

Vite 同时承担两个角色：

1. 开发时启动原生 ES module dev server，并提供快速热更新。
2. 生产构建时把 React、CSS 和应用代码打包为可部署的静态文件。

开发命令：

```bash
pnpm --dir web/admin dev
```

生产构建：

```bash
pnpm --dir web/admin build
```

`index.html` 是 Vite 模块图的入口，不需要由 FastAPI 模板引擎渲染。最终 `dist/` 是生成物，所以被 Git 忽略。

## 4. 为什么开发代理比直接开启 CORS 更合适

浏览器访问 `http://127.0.0.1:5173`，React 请求相对路径 `/api/v1/...`。Vite 把 `/api` 代理到默认的 `http://127.0.0.1:8000`。

从浏览器视角，页面和 API 仍是同一个 origin：

```text
Browser -> 127.0.0.1:5173/api/... -> Vite proxy -> 127.0.0.1:8000
```

好处：

- 不需要为本地开发放宽 FastAPI CORS。
- Cookie 的 SameSite 和 origin 语义接近未来同站点部署。
- 前端 API client 不硬编码后端主机。
- 生产环境可用 Nginx/Caddy/网关复制同样的“静态页面 + `/api` 反向代理”结构。

如果本地 8000 被占用，可以仅对 Vite 进程设置：

```bash
GUOJING_API_PROXY_TARGET=http://127.0.0.1:8765 pnpm --dir web/admin dev
```

该变量只在 Vite 配置进程中读取，不进入客户端 bundle。

## 5. 集成时发现的 Cookie Path 缺陷

第五模块最初把 Session Cookie 和 CSRF Cookie 都设置为：

```text
Path=/api/v1/admin
```

Session Cookie 没有问题：它是 HttpOnly，页面脚本本来就不应该读取，浏览器会在请求管理 API 时自动附带。

CSRF Cookie 不同。React 页面位于 `/`，浏览器只允许页面脚本通过 `document.cookie` 读取当前页面 Path 可见的 Cookie。API Path 下的 Cookie 对根页面不可见，前端无法把值复制到 `X-CSRF-Token`，写请求会得到 403。

修正后的范围：

| Cookie | HttpOnly | Path | 原因 |
|---|---|---|---|
| `guojing_admin_session` | 是 | `/api/v1/admin` | 只由浏览器发给管理 API |
| `guojing_admin_csrf` | 否 | `/` | 页面能读取，API 请求也会携带 |

Cookie Path 不是可靠的权限隔离机制。CSRF 的安全性来自：

- 不可预测的随机值；
- Cookie 与自定义 Header 必须一致；
- 服务端还要与当前 Session 中的摘要一致。

真实浏览器联调确认了两个 Path，并成功创建工作区。这说明为什么跨模块测试不能只靠单元测试替代。

## 6. 类型化 API client

所有网络行为集中在 `src/api/client.ts`：

- 自动使用相对 `/api/v1/admin` 路径。
- 设置 `credentials: same-origin`。
- 写请求读取 CSRF Cookie 并添加 Header。
- 没有 CSRF Cookie 时在发出请求前失败。
- 把非 2xx 响应转换为带 `status` 和 `detail` 的 `ApiError`。
- 统一解析 FastAPI 的字符串、对象和列表错误结构。

组件不直接调用 `fetch`，也不重复拼 Header。这相当于 Java 前端或客户端中的一个小型 typed gateway：传输协议的变化集中在一个适配器里。

TypeScript 接口提供编译期帮助，但 `response as T` 不会在运行时验证服务端 JSON。当前关键编辑文档额外有轻量结构检查；未来如果 API 演化频繁，可以从 OpenAPI 生成类型，或在边界加入 Zod 等运行时 schema。现在没有为了可能性提前增加依赖。

## 7. 认证状态机

`App` 使用三个值表达启动状态：

- `undefined`：正在调用 `/auth/me` 探测已有会话。
- `null`：匿名，显示登录页。
- `AdminSession`：已认证，显示管理台。

这比额外维护 `loading`、`loggedIn`、`user` 三个可能互相矛盾的布尔状态更容易推理。

启动时 401 是正常状态，不代表应用故障；网络中断或 500 才显示连接错误。任何后续 API 返回 401，feature 会通知 App 回到登录页。

开发模式使用 React StrictMode，因此 effect 可能被执行两次来暴露不安全副作用。真实联调日志里会看到两次只读 `/me` 和列表请求；生产构建不会进行这次开发期重复挂载。GET 必须保持幂等，写操作不会放在自动 effect 中。

## 8. 工作区与乐观锁

编辑器始终保存后端返回的 `workspace.version`：

```text
打开版本 1
  -> PUT expected_version=1
  -> 后端返回版本 2
  -> 下一次 promote expected_version=2
```

如果另一个浏览器标签已保存，后端返回 409。网页不会自动重试 PUT，因为那可能覆盖别人的内容，而是明确要求“重新载入后再编辑”。

Java 对照：这和 JPA `@Version` / `OptimisticLockException` 的业务语义一致。区别是 Web API 必须把版本显式放入请求，并把冲突翻译成用户可以决定的界面状态。

编辑器有意要求：

1. 修改后先保存。
2. 有未保存内容时禁用校验和提升。
3. 校验通过后才启用提升按钮。
4. 提升成功明确说明“尚未公开发布”。

这防止管理员把“保存草稿”“生成正式修订”“公开发布”三个不同动作混为一谈。

## 9. 为什么第一版是 JSON 编辑器

教程图包含节点、转移、锚点、截图资源、候选来源和复核状态。直接做完整可视化编辑器会同时引入：

- 动态表单数组；
- 图连接与拖拽；
- 节点局部校验；
- 截图预览与锚点框选；
- 并发合并 UI；
- API 与认证联调。

一次解决所有问题会很难判断故障究竟来自数据契约还是交互组件。JSON MVP 让完整后端文档都可编辑和验证，是一条“窄但贯通”的 vertical slice。

它的限制也很明确：只适合开发者或技术管理员，不是最终内容运营体验。下一步可在保持 API client 和工作区状态机不变的前提下，把 textarea 逐步替换为结构化表单与节点编辑器。

## 10. 测试分层

### Vitest

Vitest 是测试运行器，复用 Vite/TypeScript 配置。它类似 JUnit 平台负责发现、执行和报告测试。

### jsdom

jsdom 在 Node 进程中模拟 DOM 和 Cookie 基本行为，运行快，但不是真正 Chrome。它适合多数组件测试，不适合证明浏览器全部安全属性和布局。

### React Testing Library

测试通过 label、role 和可见文本操作页面，而不是读取组件内部 state。这会反向促进可访问性：用户名输入必须有 label，错误必须有 `role=alert`，状态提示使用 `role=status`。

### 真实 Playwright 联调

本模块还启动真实 FastAPI、SQLite、Vite 和 Chromium，验证：

- 真实管理员登录。
- Session/CSRF Cookie Path。
- Vite `/api` 代理。
- 新建工作区的 CSRF 写请求。
- 页面刷新后的会话恢复。
- 空工作区问题列表。
- 桌面和 390px 手机宽度布局。

Playwright 截图和会话文件属于本地检查产物，已被 Git 忽略。

## 11. 质量门

统一命令：

```bash
pnpm --dir web/admin check
```

依次运行：

1. Prettier 格式检查。
2. ESLint 规则检查，包括 React Hooks。
3. TypeScript strict 类型检查。
4. Vitest/Testing Library 行为测试。
5. Vite 生产构建。

`build` 输出当前约 202 KB JavaScript，gzip 后约 64 KB。未引入 UI 组件库和状态库，使初始 bundle 保持简单。

后端仍独立执行 pytest、Ruff、mypy、uv lock 和 Alembic 测试。前端上线不能以牺牲后端回归为代价。

## 12. 当前限制

- JSON 编辑器没有字段级中文解释、自动补全或语法高亮。
- 页面刷新会回到工作区列表，没有 URL 路由和深链接。
- 没有工作区删除、搜索和分页。
- 没有正式修订列表与“发布”按钮。
- 没有从 OpenAPI 自动生成 TypeScript 类型。
- 没有生产静态文件托管配置；Vite dev server 不能用于生产。
- 没有端到端测试文件进入 CI；当前 Playwright 是本地验收流程。
- 后端校验消息仍为英文，页面只做忠实展示。

## 13. 推荐继续思考的问题

1. 为什么 Session Cookie 可以限制在 API Path，而 CSRF Cookie 需要覆盖页面和 API 的共同 Path？
2. 如果前后端部署为不同 origin，`SameSite`、CORS、`credentials` 和 CSRF 设计要怎样一起变化？
3. 为什么遇到 409 时自动用新版本号重试 PUT 可能造成数据丢失？
4. 哪些状态应该留在组件，哪些重复出现后才值得进入全局 store？
5. OpenAPI 生成类型能解决编译期漂移，但为什么仍不能完全替代运行时校验？

## 14. 官方参考

- [React：在现有项目中加入 React](https://react.dev/learn/add-react-to-an-existing-project)
- [React：使用 TypeScript](https://react.dev/learn/typescript)
- [Vite：Getting Started](https://vite.dev/guide/)
- [Vite：版本与 Node 支持策略](https://vite.dev/releases)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
