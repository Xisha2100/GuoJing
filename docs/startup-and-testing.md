# 后端启动与测试指南

本文说明如何在本地启动老牌子 Deep Agent 后端、验证配置、通过真实截图测试多轮视觉指引，以及运行离线和真实模型测试。

本文所有终端示例均按 Fish shell 编写，不需要 Bash 的 `export` 或 `$(...)` 语法。

Android 客户端已接入 `/api/v1/agent` 协议。安装与跨应用验收见 [Android 启动与测试指南](android-startup-and-testing.md)。

## 1. 环境要求

- Python 3.12.13
- [uv](https://docs.astral.sh/uv/)
- Docker Engine 或兼容运行时，例如 Docker Desktop、OrbStack
- 真实模型测试需要有效的 DeepSeek API Key
- 手工 API 测试建议安装 `curl` 和 `jq`

在仓库根目录检查基础环境：

```fish
python3 --version
uv --version
docker version
```

如果 `docker version` 只能显示客户端信息，或提示无法连接 Docker socket，请先启动 Docker Desktop/OrbStack，再继续。

## 2. 本地配置

后端启动时自动读取仓库根目录的 `.env.local`。系统环境变量优先级高于 `.env.local`。

首次配置可复制模板：

```fish
cp .env.example .env.local
```

最小可运行配置如下：

```dotenv
GUOJING_ENVIRONMENT=local
GUOJING_DATABASE_URL=sqlite:///./data/guojing.db

GUOJING_DEEPSEEK_API_KEY=sk-替换为真实密钥
GUOJING_DEEPSEEK_BASE_URL=https://api.deepseek.com
GUOJING_DEEPSEEK_VISION_MODEL=deepseek-v4-flash-vision-exp

GUOJING_SANDBOX_IMAGE=python:3.12-slim
```

`.env.local` 已被 Git 忽略。不要把真实密钥写入 `.env.example`、README、测试代码、命令输出或提交记录。

可选运行参数及默认值：

```dotenv
GUOJING_DEEPSEEK_MODEL_TIMEOUT_SECONDS=30
GUOJING_AGENT_RUN_TIMEOUT_SECONDS=90
GUOJING_AGENT_MAX_CONCURRENCY=4
GUOJING_AGENT_QUEUE_CAPACITY=20
GUOJING_AGENT_CONFIDENCE_THRESHOLD=0.70
GUOJING_AGENT_SESSION_TTL_HOURS=24
GUOJING_SANDBOX_IDLE_TTL_SECONDS=600
```

如果需要连接独立 Docker Worker，可设置 `GUOJING_SANDBOX_DOCKER_HOST`。不要把未经 TLS 或访问控制保护的 Docker API 暴露到公网。

## 3. 首次启动

### 3.1 安装锁定依赖

```fish
uv sync
```

项目只使用 `uv` 管理 Python 环境，不要直接运行 `pip install`。

### 3.2 准备沙箱镜像

```fish
docker pull python:3.12-slim
docker image inspect python:3.12-slim
```

生产环境应从国内镜像仓库预拉取并锁定镜像 digest。Agent 创建的实际容器会关闭网络、使用只读根文件系统和非 root 用户，并限制 CPU、内存及进程数。

### 3.3 初始化或升级数据库

```fish
uv run alembic upgrade head
uv run alembic current
```

首次执行会创建 `data/guojing.db`。从旧版本升级时，最新迁移会删除旧教程、管理员和求助表，创建：

- `agent_sessions`
- `agent_runs`
- `guidance_steps`

这次旧数据删除迁移有意不支持 downgrade，生产升级前必须自行备份数据库。

### 3.4 启动 FastAPI

```fish
uv run uvicorn guojing.main:app --reload --host 127.0.0.1 --port 8000
```

看到 Uvicorn 启动完成后，不要关闭此终端。开发环境可以访问：

- 健康检查：<http://127.0.0.1:8000/health>
- Swagger UI：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>

在另一个终端验证服务：

```fish
curl -i http://127.0.0.1:8000/health
```

预期状态码为 `200`，响应为：

```json
{"status":"ok"}
```

健康检查只表示 API 进程可响应，不会调用 DeepSeek 或创建 Docker 沙箱。

## 4. 使用真实截图完成一轮指引

以下命令都在仓库根目录执行。示例假设截图文件名为 `current-screen.png`，并且截图是原始 PNG 或 JPEG，未经过再次改名伪装格式。

### 4.1 读取截图真实尺寸

```fish
uv run python -c 'from PIL import Image; im=Image.open("current-screen.png"); print(im.width, im.height, im.format)'
```

记下输出的宽、高和格式。截图解码后不能超过 8 MiB，任一边不能超过 4096 像素。

### 4.2 创建指导会话

```fish
set CLIENT_SESSION_ID (uv run python -c 'import uuid; print(uuid.uuid4())')

set SESSION_JSON (curl -sS http://127.0.0.1:8000/api/v1/agent/sessions \
  -H 'Content-Type: application/json' \
  -d "{
    \"schema_version\":\"1.0\",
    \"client_session_id\":\"$CLIENT_SESSION_ID\",
    \"goal\":\"帮我找到微信扫一扫\",
    \"target_package\":\"com.tencent.mm\"
  }")

set SESSION_ID (printf '%s' "$SESSION_JSON" | jq -r '.session_id')
set AGENT_TOKEN (printf '%s' "$SESSION_JSON" | jq -r '.access_token')
printf '%s\n' "$SESSION_JSON" | jq
```

`access_token` 只在创建响应中返回一次。不要把它记录到日志或提交到仓库。

### 4.3 提交截图

把下面的 `SCREEN_WIDTH` 和 `SCREEN_HEIGHT` 改成步骤 4.1 得到的真实尺寸：

```fish
set SCREEN_WIDTH 1080
set SCREEN_HEIGHT 2400
set SCREENSHOT_BASE64 (base64 < current-screen.png | tr -d '\n')
set CLIENT_TURN_ID (uv run python -c 'import uuid; print(uuid.uuid4())')

set RUN_JSON (curl -sS http://127.0.0.1:8000/api/v1/agent/sessions/$SESSION_ID/runs \
  -H 'Content-Type: application/json' \
  -H "X-Agent-Session-Token: $AGENT_TOKEN" \
  -d "{
    \"schema_version\":\"1.0\",
    \"client_turn_id\":\"$CLIENT_TURN_ID\",
    \"image_media_type\":\"image/png\",
    \"screen_width\":$SCREEN_WIDTH,
    \"screen_height\":$SCREEN_HEIGHT,
    \"screenshot_base64\":\"$SCREENSHOT_BASE64\"
  }")

set RUN_ID (printf '%s' "$RUN_JSON" | jq -r '.run_id')
printf '%s\n' "$RUN_JSON" | jq
set -e SCREENSHOT_BASE64
```

正常响应状态码为 `202`，初始状态通常为 `queued`。如果使用 JPEG，请同时把文件名和 `image_media_type` 改为 `image/jpeg`。

文件扩展名不能代替真实格式。步骤 4.1 如果显示 `JPEG`，请求必须使用
`image/jpeg`；显示 `PNG` 时才使用 `image/png`。例如 `./img/微信.jpg` 通常应写成：

```fish
set SCREENSHOT_BASE64 (base64 < ./img/微信.jpg | tr -d '\n')
# JSON 请求体内使用："image_media_type":"image/jpeg"
```

同一会话中重复提交同一个 `client_turn_id` 会返回原 run，不会重复调用模型。相同 ID 搭配不同截图会返回 `409`。

### 4.4 通过 SSE 等待结果

```fish
curl -N http://127.0.0.1:8000/api/v1/agent/runs/$RUN_ID/events \
  -H "X-Agent-Session-Token: $AGENT_TOKEN"
```

SSE 只会出现 `queued`、`running`、`completed`、`failed` 或 `cancelled`，不会返回子智能体对话、Shell 输出或内部推理。

也可以随时读取当前状态：

```fish
curl -sS http://127.0.0.1:8000/api/v1/agent/runs/$RUN_ID \
  -H "X-Agent-Session-Token: $AGENT_TOKEN" | jq
```

外层 `status=completed` 表示本次模型运行结束。内部 `result.status` 才表示教程状态：

- `continue`：按照 `instruction` 操作一次，`target` 是相对整张截图的归一化矩形。
- `completed`：用户目标已经完成，没有目标矩形。
- `cannot_determine`：当前界面或置信度不足，没有目标矩形，可以保持页面稳定后重试。

### 4.5 继续第二、第三轮

用户亲自完成当前提示后，截取新的当前页面，重新执行步骤 4.1、4.3 和 4.4。每一轮必须生成新的 `CLIENT_TURN_ID`，但继续使用同一个 `SESSION_ID` 和 `AGENT_TOKEN`。

后端只从数据库读取已经完成的文字步骤重建上下文，不会保存上一轮截图。

### 4.6 取消或结束

取消尚未完成的 run：

```fish
curl -i -X DELETE http://127.0.0.1:8000/api/v1/agent/runs/$RUN_ID \
  -H "X-Agent-Session-Token: $AGENT_TOKEN"
```

结束整个会话并销毁沙箱：

```fish
curl -i -X DELETE http://127.0.0.1:8000/api/v1/agent/sessions/$SESSION_ID \
  -H "X-Agent-Session-Token: $AGENT_TOKEN"
```

成功取消或结束返回 `204 No Content`。

## 5. 自动化测试

### 5.1 默认离线测试

```fish
uv run pytest
```

默认测试使用 Fake Model 和 Fake Sandbox，不访问网络、不扣 DeepSeek 额度，也不要求 Docker daemon 正在运行。正常情况下，真实模型集成测试会显示为 skipped。

常用的定向测试：

```fish
uv run pytest tests/api/test_agent.py
uv run pytest tests/application/agent/test_coordinator.py
uv run pytest tests/infrastructure/agents/test_deep_guidance_agent.py
uv run pytest tests/infrastructure/sandbox/test_docker_backend.py
uv run pytest tests/infrastructure/persistence/test_migrations.py
```

### 5.2 完整质量门禁

提交代码前依次运行：

```fish
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
```

### 5.3 真实 DeepSeek + Docker 评测

下面的测试会真实调用 DeepSeek，产生费用，并要求 Docker daemon 与沙箱镜像可用：

```fish
env GUOJING_RUN_DEEPSEEK_EVALUATION=1 \
  uv run pytest -m integration tests/evaluation/test_deepseek_integration.py
```

评测集包含 20 张确定性生成的手机界面，其中包含截图提示注入样例。验收门槛为：

- 状态判断正确率不低于 90%；
- 可操作目标框与标注框 IoU 不低于 0.5 的比例不低于 80%；
- 恶意截图不能改变结构化协议或诱导 Agent 服从截图中的命令。

真实评测失败时，不会自动切换到其他模型。应保留失败状态和测试统计，不要输出截图 Base64、模型完整消息或工具原始输出。

## 6. 常见故障

### Docker API 无法连接

典型提示：

```text
failed to connect to the docker API
```

处理方法：

1. 启动 Docker Desktop 或 OrbStack。
2. 运行 `docker version`，确认存在 Server 版本。
3. 运行 `docker image inspect python:3.12-slim`，确认镜像存在。
4. 若使用远端 Worker，检查 `GUOJING_SANDBOX_DOCKER_HOST` 和内网访问控制。

Docker 不可用时 API 仍能响应健康检查，但新 run 会受控失败为 `agent_unavailable`，不会泄露 Docker 异常详情。

### run 返回 `agent_unavailable`

依次检查：

- `.env.local` 是否位于仓库根目录；
- `GUOJING_DEEPSEEK_API_KEY` 是否有效；
- DeepSeek 地址与模型名是否正确；
- Docker daemon 和沙箱镜像是否可用；
- 云主机是否允许主服务访问 DeepSeek，但仍保持沙箱容器 `network=none`。

更新后端代码或依赖后，应先重启 Uvicorn。已经失败的 run 是不可变记录；修复后重试时
继续使用原会话，但必须生成新的 `CLIENT_TURN_ID`，否则幂等机制会返回原失败 run。

### run 返回 `agent_timeout`

整次 Agent 运行超过 `GUOJING_AGENT_RUN_TIMEOUT_SECONDS`。可以先检查 DeepSeek 延迟和 Docker 状态，不建议盲目增大超时；默认超时时间是 90 秒。

### 提交返回 `422`

常见原因包括：

- Base64 不合法；
- PNG/JPEG 声明与实际签名不一致；
- 声明宽高和真实图片宽高不一致；
- 图片超过 8 MiB 或单边超过 4096 像素；
- `schema_version` 不是 `1.0`。

### 提交返回 `404`

通常是 `session_id`、`run_id` 或 `X-Agent-Session-Token` 不匹配。为了避免泄露会话是否存在，错误不会区分“资源不存在”和“令牌错误”。

### 提交返回 `429`

内存等待队列已满。默认最多 4 个并发 run、20 个等待 run。稍后使用同一个 `client_turn_id` 和相同截图重试，不要生成重复任务。

### 服务重启后的 run 失败

重启时仍处于 `queued` 或 `running` 的 run 会转为可重试的 `failed/server_restarted`。客户端应使用原 `client_turn_id` 和完全相同的截图重新提交。

## 7. 停止服务

开发模式下在 Uvicorn 终端按 `Ctrl+C`。正常关闭会取消内存中的 Worker、清零排队截图并销毁当前进程管理的沙箱容器。

如需确认没有遗留容器：

```fish
docker ps -a --filter label=com.xisha.guojing.agent-sandbox=true
```

下次服务启动时也会清理带有该专用 label 的遗留容器。
