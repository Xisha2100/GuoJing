# 老牌子（GuoJing）

“老牌子”是一款面向老年人和不熟悉现代智能手机操作方式的辅助应用。它在用户实际操作微信、抖音、打车、导航、网购和系统功能时，提供一步一指引，并把隐私与高风险操作的安全边界放在 AI 之外执行。

> 当前处于早期 MVP 开发阶段。仓库已经具备后端基础骨架和教程状态图领域模型，Android 客户端、管理网页、数据库与 Agent 编排尚未接入。

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
│   ├── core/                # 配置等横切能力
│   ├── domain/tutorials/    # 教程状态图与确定性业务规则
│   └── main.py              # FastAPI 应用入口
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
uv run uvicorn guojing.main:app --reload
```

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

下一模块计划实现“教程草稿发布与读取”垂直切片：

- 管理端提交教程图的 Pydantic DTO。
- DTO 与领域对象之间的显式映射。
- SQLite 草稿和发布版本持久化。
- 管理端发布 API。
- Android 只读教程 API。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
