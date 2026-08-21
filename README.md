# 老牌子（GuoJing）

“老牌子”是一款面向老年人和不熟悉现代智能手机操作方式的辅助应用。它在用户实际操作微信、抖音、打车、导航、网购和系统功能时，提供一步一指引，并把隐私与高风险操作的安全边界放在 AI 之外执行。

> 当前处于早期 MVP 开发阶段。仓库已经具备后端基础骨架、教程状态图、版本发布、教程编辑工作区、管理端认证审计、React 管理网页，以及能够读取公开教程、观察目标页面、跨 APP 框选操作目标并验证低风险结果的 Android 客户端；截图/OCR、真实文件存储与 Agent 编排尚未接入。

## 产品方向

主要交互不是让用户先学习一整套课程，而是在遇到问题时现场求助：

1. 用户点击悬浮球并说出目标。
2. 老牌子判断是否存在已录制教程。
3. 每次只显示一个操作目标，通过箭头、框选、文字和语音说明。
4. 用户亲自点击，系统观察页面变化并验证是否进入预期状态。
5. 页面不一致、风险过高或连续识别失败时暂停，并可请求家属协助。

首批计划覆盖：

- 系统功能：拍照、打电话、通讯录、图库。
- 微信：语音/视频通话、添加好友、拉群、发语音、收红包、线下支付、查看余额。
- 淘宝：搜索、筛选、评价、购物车、订单与物流。
- 滴滴：设置起终点、叫车、查看行程。
- 高德地图：搜索地点与开始导航。
- 抖音：搜索、关注、收藏和分享到微信。

## 当前架构

```text
.
├── src/guojing/
│   ├── api/                 # FastAPI HTTP 适配层
│   ├── application/         # 用例、DTO 与 Repository 端口
│   ├── core/                # 配置等横切能力
│   ├── domain/tutorials/    # 教程状态图与确定性业务规则
│   ├── infrastructure/      # SQLAlchemy / SQLite 适配器
│   └── main.py              # FastAPI 应用入口
├── migrations/              # Alembic 数据库结构历史
├── tests/                   # 与源码结构对应的测试
├── android/                 # Kotlin + Jetpack Compose 老年用户客户端
├── web/admin/               # React + TypeScript 管理网页
├── docs/learning/           # 每个模块的学习文档
├── pyproject.toml           # Python 项目、依赖和工具配置
└── uv.lock                  # 精确依赖锁
```

计划中的技术栈：

- Android：Kotlin、Jetpack Compose、AccessibilityService 与悬浮窗。
- 后端：Python 3.12、FastAPI、LangGraph、Deep Agents。
- 管理网页：React、TypeScript、Vite。
- 数据：SQLite/WAL 起步，保留迁移到 PostgreSQL 的边界。
- 中国大陆 AI 服务：阿里云百炼/Qwen、Fun-ASR、CosyVoice。

## 后端快速开始

### 环境要求

- Python 3.12.13
- [uv](https://docs.astral.sh/uv/)

项目通过 `.python-version` 指定开发解释器，通过 `pyproject.toml` 声明兼容范围，通过 `uv.lock` 固定经过验证的精确依赖。

### 安装依赖

```bash
uv sync
```

### 启动 API

```bash
uv run alembic upgrade head
uv run python -m guojing.cli create-admin --username admin
uv run uvicorn guojing.main:app --reload
```

默认数据库位于 `data/guojing.db`，可以通过 `GUOJING_DATABASE_URL` 切换地址。首次迁移后，CLI 会交互式读取并确认管理员密码，密码不会出现在命令行参数或 shell 历史中。忘记密码时可运行：

```bash
uv run python -m guojing.cli reset-admin-password --username admin
```

管理 API 使用服务端会话、HttpOnly Cookie 和 CSRF 校验。`GUOJING_ADMIN_COOKIE_SECURE=false` 只适用于本地 HTTP；staging/production 必须设置为 `true` 并通过 HTTPS 访问，否则配置校验会拒绝启动。项目提供 `.env.example` 作为变量清单，但当前不会自动读取 `.env`，需要由 shell、IDE 或部署平台注入环境变量。

启动后可访问：

- 健康检查：<http://127.0.0.1:8000/health>
- Swagger UI：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>

### 运行检查

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
```

不要使用 `pip install` 直接修改项目环境。添加依赖时使用：

```bash
uv add <package>
uv add --dev <package>
```

## 管理网页快速开始

### 环境要求

- Node.js 22.12 或更新版本（当前验证版本为 24.18.0）
- pnpm 11（项目通过 `packageManager` 固定为 11.7.0）

前端依赖只安装到项目，并由 `web/admin/pnpm-lock.yaml` 锁定；不需要全局安装 Vite、TypeScript、ESLint 或 Vitest。

先按上文启动 FastAPI，然后在另一个终端运行：

```bash
pnpm --dir web/admin install --frozen-lockfile
pnpm --dir web/admin dev
```

打开 <http://127.0.0.1:5173>。Vite 默认把同源 `/api` 请求代理到 <http://127.0.0.1:8000>，因此浏览器不需要额外 CORS 配置，并可直接使用服务端 Session Cookie 与 CSRF Cookie。

前端完整检查与生产构建：

```bash
pnpm --dir web/admin check
pnpm --dir web/admin build
```

生产环境应把 `web/admin/dist/` 静态文件和 `/api` 反向代理部署在同一站点；开发代理不是生产服务器。

## Android 客户端快速开始

### 环境要求

- JDK 17
- Android SDK Platform 37、Build Tools 37.0.0 与 Platform Tools
- Android Studio 或命令行 SDK 工具
- 设备测试需要 API 36 ARM64 系统镜像和 AVD；当前验证设备为 `Pixel_7`

项目通过 `android/gradlew` 固定 Gradle 9.4.1，通过 Version Catalog 固定 AGP、Kotlin 编译器插件和 AndroidX 版本。无需全局安装 Gradle 或 Kotlin。

先启动 FastAPI，再构建和安装 Debug 应用：

```bash
uv run alembic upgrade head
uv run uvicorn guojing.main:app --reload
cd android
./gradlew installDebug
```

Android 模拟器通过 `http://10.0.2.2:8000` 访问宿主机 FastAPI。若本机 8000 端口被占用，可让后端监听其他端口，并仅在本次构建覆盖 Debug 地址：

```bash
./gradlew installDebug \
  -PGUOJING_DEBUG_API_BASE_URL=http://10.0.2.2:18000
```

`http` 明文访问只在 Debug Manifest 中开放；Release 默认使用不可路由的 `https://api.invalid`，部署时必须通过 `-PGUOJING_API_BASE_URL=https://...` 提供真实 HTTPS 地址。

Android 检查命令：

```bash
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest
./gradlew connectedDebugAndroidTest
```

第二条命令要求已有完成启动的 Android 设备或模拟器。

## 已完成模块

### 00：后端基础骨架

- FastAPI 应用工厂。
- 类型化环境配置。
- `/health` 存活检查。
- uv 依赖管理与自动化质量检查。

学习文档：[docs/learning/00-backend-foundation.md](docs/learning/00-backend-foundation.md)

### 01：教程状态图

- 用节点和边表示已录制教程，不回放固定坐标。
- required、optional、forbidden 三类页面锚点。
- 图结构校验、页面匹配与 APP 版本兼容评估。
- 低风险步骤可在新版 APP 上验证下一状态，高风险步骤要求人工复核。

学习文档：[docs/learning/01-tutorial-state-graph.md](docs/learning/01-tutorial-state-graph.md)

### 02：Git 仓库治理

- 项目级 `.gitignore` 覆盖 Python、Android、Node、密钥和本地数据。
- README 与真实实现状态、启动命令和学习入口保持一致。
- 保持原有 GPL-3.0 授权，并明确许可证变更边界。

学习文档：[docs/learning/02-repository-hygiene.md](docs/learning/02-repository-hygiene.md)

### 03：教程草稿发布与读取

- 严格且带 `schema_version` 的 Pydantic 教程 DTO。
- 应用服务与 Repository Protocol 隔离 HTTP 和 SQLAlchemy。
- SQLite 中保存不可变修订，通过发布指针选择 Android 可见版本。
- Alembic 首次迁移、管理员 Bearer 保护和公开只读 API。

学习文档：[docs/learning/03-tutorial-publishing-and-storage.md](docs/learning/03-tutorial-publishing-and-storage.md)

### 04：教程录制与编辑工作区

- 不完整编辑文档与可发布正式教程图分离。
- 截图、Accessibility Tree、OCR 只保存脱敏资源引用，不内嵌大文件。
- Accessibility、OCR、AI 和人工候选锚点记录来源与管理员复核结果。
- 使用 `expected_version` 乐观锁防止多个网页标签页静默覆盖。
- 提升操作原子创建正式修订，但不会自动发布给 Android。

学习文档：[docs/learning/04-tutorial-authoring-workspace.md](docs/learning/04-tutorial-authoring-workspace.md)

### 05：管理端身份认证与安全审计

- Argon2id 自适应密码哈希与交互式管理员 CLI。
- 数据库仅保存摘要的服务端不透明会话，支持固定过期和主动撤销。
- HttpOnly、SameSite、Secure Cookie 与双提交 CSRF 防护。
- 持久化登录节流、统一认证错误和关键操作审计。

学习文档：[docs/learning/05-admin-authentication-and-audit.md](docs/learning/05-admin-authentication-and-audit.md)

### 06：React 管理网页 MVP

- 管理员登录、会话恢复和退出。
- 工作区列表、新建、完整 JSON 编辑、保存、校验和提升。
- 类型化 API client 集中处理 Cookie、CSRF 与 HTTP 错误。
- 将 `409` 乐观锁冲突转化为禁止静默覆盖的界面反馈。
- Vitest/Testing Library 行为测试与真实浏览器桌面、手机联调。

学习文档：[docs/learning/06-react-admin-web.md](docs/learning/06-react-admin-web.md)

### 07：Android 客户端基础与教程目录

- Gradle Wrapper、Version Catalog、AGP 9 内建 Kotlin 和 Compose 工程基础。
- 公开教程 HTTP 数据源、严格 JSON 边界、Repository 与单向数据流 ViewModel。
- 加载、内容、空数据、失败重试四类确定性界面状态。
- 大字号、清晰层级、安全区与 TalkBack 标题语义等适老化基础。
- JVM 单元测试、Lint、APK 构建和 Pixel 7 设备端 Compose 测试。

学习文档：[docs/learning/07-android-client-foundation.md](docs/learning/07-android-client-foundation.md)

### 08：Android 教程详情与逐步执行

- 读取和校验完整的已发布教程状态图，而不是把图静默扁平化为列表。
- Navigation Compose 串联目录、详情和执行状态，并正确处理返回栈。
- 纯 Kotlin 执行引擎逐节点前进，UI 不能绕过安全策略改写进度。
- 多分支、循环、过期节点和数据损坏安全暂停；金融与不可逆步骤硬拦截。
- 明确标注当前为手动确认的演示模式，不冒充已验证第三方 APP 页面。
- 27 个 JVM 测试、6 个 Pixel 7 设备测试和真实 FastAPI 临时数据库联调。

学习文档：[docs/learning/08-android-tutorial-execution.md](docs/learning/08-android-tutorial-execution.md)

### 09：Android 本地页面观察

- 声明最小事件范围的 `AccessibilityService`，由用户在独立披露后主动前往系统设置开启。
- 仅在教程执行期间注册观察请求，并在读取节点树前校验目标包名和隐私模式。
- `capture_paused` 完全不读取节点树，密码节点不提取文字，`local_only` 证据只能留在内存和本机。
- 原始语义节点即时转换成 `anchor_id + confidence + structure_score`，不保存聊天、联系人或余额文本。
- Kotlin 页面匹配规则与后端 Python 参考实现保持同一阈值和权重，输出 matched / uncertain / mismatch。
- 40 个 JVM 测试、8 个 Pixel 7 设备测试、Android Lint 和 APK 构建通过。

学习文档：[docs/learning/09-android-page-observation.md](docs/learning/09-android-page-observation.md)

### 10：Android 跨 APP 可见引导与结果验证

- 将已匹配锚点的脱敏归一化边界传给引导层，不携带第三方页面原文。
- 使用 `TYPE_ACCESSIBILITY_OVERLAY` 绘制大字步骤卡、箭头和目标框；窗口不接收触摸，用户仍亲自操作目标 APP。
- 浮层只在目标包名和 source node 强匹配时显示，切换到其他 APP 或证据变弱时立即隐藏。
- 用户声明已操作后切换到 target node 观察；连续两次强匹配才允许低风险步骤推进。
- 不确定、不匹配、隐私暂停都保持在当前步骤，并提示用户停止重复操作。
- 纯 Kotlin 布局规划、ViewModel 状态机和 Pixel 7 真实跨 APP 闭环均已验证。

学习文档：[docs/learning/10-android-guidance-overlay.md](docs/learning/10-android-guidance-overlay.md)

## 教程 API

管理端先登录；成功响应会设置会话 Cookie 和 CSRF Cookie：

```http
POST /api/v1/admin/auth/login
Content-Type: application/json

{"username":"admin","password":"..."}
```

读取接口由浏览器自动携带 HttpOnly 会话 Cookie。所有 `POST`、`PUT` 等状态变更请求还必须把 `guojing_admin_csrf` Cookie 的值复制到 `X-CSRF-Token` 请求头；React 管理网页已在一个类型化 API client 中统一封装该行为。

管理端创建和继续编辑工作区：

```http
POST /api/v1/admin/tutorial-drafts
GET  /api/v1/admin/tutorial-drafts
GET  /api/v1/admin/tutorial-drafts/{workspace_id}
PUT  /api/v1/admin/tutorial-drafts/{workspace_id}
POST /api/v1/admin/tutorial-drafts/{workspace_id}/validate
POST /api/v1/admin/tutorial-drafts/{workspace_id}/promote
```

`PUT` 和 `promote` 必须携带当前 `expected_version`。版本落后时返回 `409`，客户端应重新读取并让管理员决定如何合并。`promote` 只生成未发布的正式修订，仍需调用下面的发布 API。

管理端保存草稿：

```http
POST /api/v1/admin/tutorials/drafts
```

发布明确的修订：

```http
POST /api/v1/admin/tutorials/{graph_id}/revisions/{revision_number}/publish
```

Android 只会读取已发布内容：

```http
GET /api/v1/tutorials
GET /api/v1/tutorials/{graph_id}
```

## 隐私与安全原则

- 用户始终亲自点击，老牌子不自动操作第三方 APP。
- 待机状态不截图、不录音；只有可见的帮助会话才观察页面。
- 通讯录、图库、聊天、余额、红包和支付页面优先或强制本地处理。
- 密码、验证码和生物识别阶段完全暂停采集。
- 金融、不可逆社交操作和账号变更由确定性安全策略拦截，不能只依赖模型提示词。
- 成功的通用指引只能生成待审核教程草稿，不能自动发布。

## 学习型开发流程

本项目既要产出产品，也要记录实现过程。每个模块遵循：

1. 实现代码。
2. 编写并运行测试。
3. 生成 `docs/learning/NN-*.md`。
4. 解释架构、调用链、取舍、风险和 Java/Python 对照。
5. 暂停，由项目所有者理解并确认后进入下一模块。

## 下一步

下一模块将建立截图求助入口和本地隐私预处理：允许用户主动导入截图并提出问题，在上传或调用模型前识别敏感区域、形成可审计的脱敏结果，并把“已录制教程匹配”与“尚无教程时的基础指引”分成明确路径。OCR、视觉模型和 Agent 编排会按可测试端口逐步接入，不会绕过现有执行安全策略。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
