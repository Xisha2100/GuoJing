# 老牌子（GuoJing）

“老牌子”是一款面向老年人和不熟悉现代智能手机操作方式的辅助应用。它在用户实际操作微信、抖音、打车、导航、网购和系统功能时，提供一步一指引，并把隐私与高风险操作的安全边界放在 AI 之外执行。

> 当前处于早期 MVP 开发阶段。仓库已经具备后端基础骨架、教程状态图、版本发布、教程编辑工作区、管理端认证审计、React 管理网页，以及能够读取公开教程、观察目标页面、跨 APP 框选操作目标并验证低风险结果的 Android 客户端。Android 现已支持用户主动导入截图、在本机生成隐私遮挡副本，并在显式确认后发送受限求助请求；本地 ML Kit OCR 可提出隐私区域建议，但必须由用户逐项确认，模型回答与 Agent 编排尚未接入。

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

### 11：Android 截图求助与本地脱敏

- 从教程目录进入“截图问一问”，即使后端离线或没有对应教程也能使用入口。
- 使用系统 Photo Picker 只读取用户主动选择的一张图片，不申请整个图库的读取权限。
- 将临时 `content://` URI 解码、限制为最长边 1440 像素并重新编码为本次会话的内存副本，不保存 URI 或原图文件。
- 用户逐处框选姓名、头像、电话、地址、余额、订单号和二维码，实际输出通过 Canvas 把像素永久替换为黑色。
- 问题文本与“已框选”或“确认无敏感内容”组成确定性门槛；原图在脱敏成功后尽力清零。
- 当前结果明确标记为“尚未发送给 AI”，不会把本地预览冒充 OCR 或模型回答。

学习文档：[docs/learning/11-android-screenshot-privacy.md](docs/learning/11-android-screenshot-privacy.md)

### 12：截图求助请求契约与显式发送

- 使用严格的 `schema_version=1.0` JSON 契约描述问题、处理意图、图片尺寸、脱敏摘要和显式发送同意。
- Android 端将“查找已录制教程”和“没有教程，先看基础指引”建模为两个确定性路由，不让模型猜意图。
- 只有用户勾选发送确认后，客户端才会把本地脱敏 JPEG 发送到 `/api/v1/help-requests`。
- 后端限制图片为 JPEG、最长边 1440、最多 8 MiB，并校验 Base64、JPEG 标记和 SHA-256；处理完成后立即清零临时缓冲，不写数据库或对象存储。
- 服务端只返回“已接收、下一步路由和图片已丢弃”的收据；当前响应以 `received` 状态进入可查询的处理生命周期，不冒充 OCR、视觉模型或 Agent 已经回答。

学习文档：[docs/learning/12-help-request-contract.md](docs/learning/12-help-request-contract.md)

### 13：OCR 能力边界与可替换证据合同

- 定义 `OnDevice`、`BackendWorker` 和 `VisionModel` 三种策略，但暂不绑定具体 OCR SDK。
- 只有本地会话或已经脱敏的截图可以进入 OCR；网络策略还必须显式允许联网。
- OCR 原文只在一次识别会话内使用，进入观察结果的只有 `anchor_id`、置信度和归一化边界。
- OCR 证据来源与 Accessibility 证据分开标记，继续交给现有确定性页面匹配和风险策略。

学习文档：[docs/learning/13-ocr-evidence-contract.md](docs/learning/13-ocr-evidence-contract.md)

### 14：ML Kit 本地 OCR 适配器

- 使用打包式 ML Kit 中文与 Latin 模型，首次识别不依赖动态模型下载。
- 将 `Task<Text>` 适配为可取消的 Kotlin suspend API，并在成功、失败和取消路径传播结果。
- 以行级文字和像素矩形为输入，转换为归一化 `OcrTextBlock`，不把整段 OCR 原文写入页面观察结果。
- Bitmap、recognizer 和临时截图都遵循会话生命周期；Pixel 7 已验证程序生成文字图片可以被识别。

学习文档：[docs/learning/14-mlkit-local-ocr.md](docs/learning/14-mlkit-local-ocr.md)

### 15：OCR 隐私区域建议与逐项确认

- 将 OCR 原文在本机分类为电话号码、邮箱、身份证号、银行卡号、余额、订单和地址等建议类型，不把原文放进 UI 状态。
- 橙色框表示待审核建议，用户点“遮住这处”后才变成黑色脱敏区域，也可以明确选择“不是隐私”。
- Pending 建议会阻止生成脱敏副本；OCR 失败不会阻塞手动框选。
- Compose 和 ViewModel 测试覆盖建议可见性、接受/拒绝状态和隐私门槛。

学习文档：[docs/learning/15-ocr-privacy-suggestions.md](docs/learning/15-ocr-privacy-suggestions.md)

### 16：截图求助处理结果契约

- 定义 `received`、`processing`、`needs_human_review` 和 `guidance_ready` 四个受限处理状态，状态只能向前迁移。
- 新增状态查询接口；服务端只暂存有限的请求元数据，不保存截图。模块 16 的内存原型重启后会失效，模块 21 起由 SQLite Repository 跨进程保存。
- 基础指引只允许返回需要用户亲自完成的说明步骤，不携带坐标、手势、Accessibility 操作或支付命令。
- Android 提供严格 JSON parser 和“刷新处理状态”入口，未知状态或不安全的 guidance 形状会 fail closed。

学习文档：[docs/learning/16-help-request-processing-results.md](docs/learning/16-help-request-processing-results.md)

### 17：求助处理器端口与确定性安全分支

- 用 `HelpRequestProcessor` 端口隔离请求生命周期和未来的 OCR、检索或 DeepAgent 实现。
- 处理器只接收图片已丢弃后的元数据；录制教程请求在缺少页面证据时进入人工复核。
- 通用求助请求可以使用已审核的本地基础指引目录，仍然只返回人工操作说明。
- `HelpRequestService.process()` 统一执行 `received → processing → review/guidance`，处理器不能自行修改状态。

学习文档：[docs/learning/17-help-request-processor.md](docs/learning/17-help-request-processor.md)

### 18：无模型基础指引目录

- 将没有已录制教程的请求路由到小型、可审阅的基础指引目录。
- 指引内容由普通文本步骤组成，不包含坐标、手势、节点动作或自动化函数。
- 录制教程路径不会因为缺少截图而猜测下一步，而是明确转人工复核。

学习文档：[docs/learning/18-basic-guidance-catalog.md](docs/learning/18-basic-guidance-catalog.md)

### 19：管理员人工复核闭环

- 管理员通过现有会话和 CSRF 保护读取待复核求助元数据。
- 管理员只能发布经过领域规则校验的人工指引，服务端不会把截图或问题正文暴露给复核接口。
- 危险的支付、转账、密码、验证码、账号删除等操作词会被领域层拒绝，不能仅靠前端约束。
- 发布动作写入既有管理员审计日志，便于后续家属端和审核工作台复用。

学习文档：[docs/learning/19-human-review.md](docs/learning/19-human-review.md)

### 20：端到端安全收口

- 重复提交复用同一个 `client_request_id` 的服务端收据，降低网络重试造成重复处理的风险。
- Android 状态查询校验请求 ID、客户端 ID、意图和处理路由的一致性，错配响应 fail closed。
- Android 端同样拒绝危险指引文字，并在隐私建议超过上限时阻止发送而不是静默截断。
- Python、Android JVM、Lint 和设备测试共同覆盖提交、处理、复核、发布和失败路径。

学习文档：[docs/learning/20-end-to-end-hardening.md](docs/learning/20-end-to-end-hardening.md)

### 21：求助结果持久化与 TTL

- 用 `HelpRequestRepository` 端口隔离状态机和数据库实现，单元测试仍可注入内存替身。
- 默认 FastAPI 应用使用 SQLite 保存请求元数据、处理状态和已审核指引，不保存截图或 Base64。
- `client_request_id`、请求指纹和数据库唯一约束共同保证跨进程幂等；不同内容复用同一 ID 会被拒绝。
- 结果带 TTL 和容量上限，读取、列表和创建时都会清理过期记录，避免无限保留家属/复核信息。

学习文档：[docs/learning/21-help-request-persistence.md](docs/learning/21-help-request-persistence.md)

### 22：受控证据 Envelope 与隐私边界

- 用不可变 `EvidenceEnvelope` 表达包名、版本、锚点置信度和归一化边界，不提供 raw OCR、Accessibility 文本或图片字节字段。
- `local_only` 证据在网络边界 fail closed；只有显式允许联网且未过期的脱敏摘要可以进入后端。
- 新增证据 API、短 TTL 清理、SQLite Repository 和严格 `schema_version=1.0` DTO。
- 证据与求助结果分表保存，结果删除时外键级联删除证据，并限制单请求和全局证据数量。

学习文档：[docs/learning/22-evidence-envelope.md](docs/learning/22-evidence-envelope.md)

### 23：教程检索与版本匹配

- 按 Android 包名加载当前已发布教程，逐节点调用既有确定性锚点匹配。
- 结合版本兼容评估选择最高分候选；新版本、弱证据、旧节点和无匹配都会返回可解释的停机原因。
- 稳定排序保证同一证据得到可复现结果，不让模型猜测教程或绕过金融/不可逆操作复核。

学习文档：[docs/learning/23-tutorial-selection.md](docs/learning/23-tutorial-selection.md)

### 24：LangGraph-compatible 求助编排骨架

- 用可注入的 Python 工作流连接求助结果、受控证据、教程匹配和基础指引处理器。
- 教程分支支持 `awaiting_evidence` 可恢复检查点；不确定或版本变化会停在人审，不重复推进状态。
- 编排状态不包含截图、OCR 原文或 Android 操作，未来可映射到 LangGraph/Deep Agents 节点而不改变领域规则。

学习文档：[docs/learning/24-help-request-workflow.md](docs/learning/24-help-request-workflow.md)

### 25：模型适配器与安全降级

- 定义最小 `GuidanceModel` 端口，模型只接触图片已丢弃后的元数据。
- 严格解析人工说明 JSON，拒绝未知字段、自动操作步骤和金融/不可逆危险词。
- 已抛出的模型异常或输出不合规时统一转人工复核；真实模型接入前仍需实现独立 deadline/lease，教程请求不能绕过证据匹配。
- 当前不绑定模型 SDK，未来可将 LangGraph/Deep Agent、Qwen 或 OpenAI-compatible 客户端包在适配器之后。

学习文档：[docs/learning/25-model-adapter-safety.md](docs/learning/25-model-adapter-safety.md)

### 27：生产求助工作流入口与可轮询检查点

- `main.py` composition root 统一装配求助服务、证据服务、教程匹配器和基础指引处理器，管理员处理入口不再绕过模块 23–25。
- `POST /api/v1/admin/help-requests/{request_id}/process` 会执行一次有边界的工作流；通用指引进入 `completed`，教程强匹配进入 `tutorial_matched` 并暂停人工确认。
- 工作流阶段、匹配状态、graph/node/revision 安全摘要持久化到求助结果，客户端可通过原 status endpoint 轮询，服务重启后仍能读取。
- Android 状态解析器识别新阶段和候选元数据，对未知值或阶段/处理状态矛盾的响应 fail closed；不显示截图、OCR 原文或节点树。

学习文档：[docs/learning/27-production-help-workflow-entry.md](docs/learning/27-production-help-workflow-entry.md)

### 28：服务端证据时间与保留边界

- 服务端限制客户端证据的采集时间窗口与 TTL，响应返回实际生效的过期时间。
- `received_at` 决定最新记录，单个求助和全局证据集合均有明确上限。
- 重用同一个 `evidence_id` 只能得到同一提交结果，不能覆盖为不同证据。

学习文档：[docs/learning/28-server-evidence-boundaries.md](docs/learning/28-server-evidence-boundaries.md)

### 29：求助结果乐观并发控制

- 每个求助状态携带 `state_version`；转移时 SQL 使用 `WHERE state_version = expected`。
- 旧 worker 的陈旧写入返回冲突，而不会覆盖已确认的终态。
- 处理器故障和状态落库冲突使用不同异常边界，冲突不会被误降级为新的状态写入。

学习文档：[docs/learning/29-help-request-optimistic-concurrency.md](docs/learning/29-help-request-optimistic-concurrency.md)

### 30：模型最小任务上下文与 deadline

- 模型得到通用任务、人工操作安全规则和时区感知 deadline，但不会得到截图、OCR、原始问题或 Android 控制器。
- 单次模型调用超时后立即转人工复核；未退出的调用占用唯一槽位，后续请求 fail closed。
- 真实 Deep Agent / HTTP 适配器必须将 deadline 传入连接、读取和总超时配置。

学习文档：[docs/learning/30-model-context-and-deadline.md](docs/learning/30-model-context-and-deadline.md)

### 评审修复（模块 10–20 安全收口）

- 求助接口在 JSON 解析前限制请求体，并让校验错误、成功响应和状态查询统一禁止缓存且不回显截图或问题正文。
- 处理器异常安全转人工复核；重复提交固定返回接收收据；人工复核先记录可重放的 `*_requested` 审计意图。
- Android 发送重试复用同一 `client_request_id`，严格关联收据的客户端 ID、意图、路由、状态和状态地址。
- 浮层绑定 observation 序列，版本漂移仅允许低风险试运行并强制目标页确认；OCR block 一对一分配；隐私收据和危险指引字段增加最终不变量校验。

学习文档：[docs/learning/26-review-remediation.md](docs/learning/26-review-remediation.md)

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

求助工作流接口：

```http
POST /api/v1/help-requests
POST /api/v1/help-requests/{request_id}/evidence
GET  /api/v1/help-requests/{request_id}
POST /api/v1/admin/help-requests/{request_id}/process
```

管理员处理接口需要登录会话和 CSRF 请求头。状态响应中的 `workflow_stage`、`tutorial_match` 与 `tutorial_plan` 只包含安全的阶段、教程标识和已审查的低风险 transition ID；它们不是自动点击或支付授权。

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

模块 53 将模板目录和导入操作接入 React 管理台。模块 52 的草稿安全边界仍保留：必须验证、校验和显式发布。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
