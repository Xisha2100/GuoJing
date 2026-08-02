# 老牌子（GuoJing）

“老牌子”是一款面向老年人和不熟悉现代智能手机操作方式的辅助应用。它在用户实际操作微信、抖音、打车、导航、网购和系统功能时，提供一步一指引，并把隐私与高风险操作的安全边界放在 AI 之外执行。

> 当前处于早期 MVP 开发阶段。仓库已经具备后端基础骨架、教程状态图，以及教程草稿、发布和只读查询的 SQLite 垂直切片；Android 客户端、管理网页与 Agent 编排尚未接入。

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
export GUOJING_ADMIN_API_TOKEN="$(openssl rand -hex 32)"
uv run alembic upgrade head
uv run uvicorn guojing.main:app --reload
```

默认数据库位于 `data/guojing.db`。可以通过 `GUOJING_DATABASE_URL` 切换地址。管理写接口在没有配置至少 32 字符的 `GUOJING_ADMIN_API_TOKEN` 时保持关闭；令牌仅是单管理员 MVP 的启动保护，不是最终家属账号系统。项目提供 `.env.example` 作为变量清单，但当前不会自动读取 `.env`，需要由 shell、IDE 或部署平台注入环境变量。

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

## 教程 API

管理端保存草稿：

```http
POST /api/v1/admin/tutorials/drafts
Authorization: Bearer <GUOJING_ADMIN_API_TOKEN>
```

发布明确的修订：

```http
POST /api/v1/admin/tutorials/{graph_id}/revisions/{revision_number}/publish
Authorization: Bearer <GUOJING_ADMIN_API_TOKEN>
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

下一模块将在确认本模块后设计“教程录制/编辑工作流”：先定义管理端如何逐步生成节点、锚点和转移，再决定网页编辑器与截图标注的数据协议。不会让 AI 生成的草稿绕过人工发布。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
