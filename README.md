# 老牌子（GuoJing）

老牌子当前优先交付后端视觉指引智能体：客户端提交用户目标和当前手机截图，后端通过 Deep Agents 调用界面分析与指引审校两个子智能体，每轮只返回一个可见目标的结构化操作提示。智能体不会控制手机，也不会代替用户点击。

> 当前阶段只验收后端。仓库中的 Android 应用仍是旧教程协议客户端，与新的 `/api/v1/agent` API 暂不兼容；Android 构建不是本阶段质量门禁。旧教程后端、人工审核、管理员系统和 React 管理网页已经删除，Android 接入将在第二阶段完成。

## 已实现架构

```text
截图 + 目标
    │
    ▼
FastAPI 会话/run API ──► 有界内存队列（4 并发、20 等待）
    │                              │
    │                              ▼
    │                    Deep Agents 主智能体
    │                       │            │
    │                       ▼            ▼
    │                  ui-analyst   guidance-reviewer
    │                       └──────┬─────┘
    │                              ▼
    └──── SSE / GET ◄──── 单步 GuidanceDecision
                                   │
                                   ▼
                    无公网、只读、非 root Docker 沙箱
```

- 主智能体由真实的 `deepagents.create_deep_agent()` 创建。
- 模型使用 `ChatOpenAI` 访问 DeepSeek OpenAI 兼容 Chat Completions 接口，默认模型为 `deepseek-v4-flash-vision-exp`。
- `ui-analyst` 继承本轮多模态截图上下文；`guidance-reviewer` 是隔离子智能体，只接收界面分析文本和候选步骤。两者必须各调用一次且顺序固定。
- 最终响应通过 `ToolStrategy(GuidanceDecisionOutput)` 校验。低于置信度阈值的候选步骤会降级为 `cannot_determine`。
- 每个会话使用一个临时 Docker 容器；容器无网络、无宿主机挂载和凭据，根文件系统只读，限制为 0.5 CPU、512 MiB、64 PIDs。
- 截图只存在于请求内存、可清零的 `bytearray` 和沙箱临时目录。数据库不保存截图、Base64、完整模型消息、内部推理或原始工具输出。
- 服务启动时把未完成 run 标记为可重试的 `failed/server_restarted`，并清理遗留沙箱。

## 项目结构

```text
src/guojing/
├── api/                    # 会话、run、SSE 与输入边界
├── application/agent/      # 用例、队列和端口
├── core/                   # 类型化配置
├── domain/                 # 结构化指引与状态约束
├── infrastructure/agents/  # Deep Agents + DeepSeek 组合
├── infrastructure/sandbox/ # Docker SandboxBackend
├── infrastructure/persistence/
└── main.py                 # FastAPI 组合根
migrations/                 # 保留历史迁移，并迁移到三张 Agent 表
tests/                      # 默认使用 Fake Model / Fake Sandbox
android/                    # 暂时保留的旧客户端，第二阶段重构
```

## 本地运行

要求 Python 3.12.13、uv 和 Docker Engine。先确保沙箱镜像已经存在；默认使用 `python:3.12-slim`，生产环境应使用国内镜像仓库中的固定摘要镜像。

```bash
uv sync
docker pull python:3.12-slim
uv run alembic upgrade head
export GUOJING_DEEPSEEK_API_KEY='你的密钥'
uv run uvicorn guojing.main:app --reload
```

API 不自动读取 `.env`。可参考 [`.env.example`](.env.example)，由 shell、IDE、容器平台或密钥管理服务注入变量。启动后可访问：

- 健康检查：<http://127.0.0.1:8000/health>
- Swagger UI：<http://127.0.0.1:8000/docs>

## API 使用

创建会话，`access_token` 只返回一次，服务端只保存其 SHA-256 摘要：

```bash
curl -sS http://127.0.0.1:8000/api/v1/agent/sessions \
  -H 'Content-Type: application/json' \
  -d '{
    "schema_version":"1.0",
    "client_session_id":"11111111-1111-4111-8111-111111111111",
    "goal":"帮我找到微信扫一扫",
    "target_package":"com.tencent.mm"
  }'
```

将响应中的 `session_id` 和 `access_token` 用于后续请求。截图只接受 JPEG/PNG，解码后不超过 8 MiB，单边不超过 4096 像素，声明尺寸必须与图片一致：

```bash
SCREENSHOT_BASE64="$(base64 < current-screen.png | tr -d '\n')"

curl -sS http://127.0.0.1:8000/api/v1/agent/sessions/SESSION_ID/runs \
  -H 'Content-Type: application/json' \
  -H 'X-Agent-Session-Token: ACCESS_TOKEN' \
  -d "{
    \"schema_version\":\"1.0\",
    \"client_turn_id\":\"22222222-2222-4222-8222-222222222222\",
    \"image_media_type\":\"image/png\",
    \"screen_width\":1080,
    \"screen_height\":2400,
    \"screenshot_base64\":\"$SCREENSHOT_BASE64\"
  }"
```

提交返回 `202`。通过 SSE 等待结果，或使用 GET 恢复：

```bash
curl -N http://127.0.0.1:8000/api/v1/agent/runs/RUN_ID/events \
  -H 'X-Agent-Session-Token: ACCESS_TOKEN'

curl -sS http://127.0.0.1:8000/api/v1/agent/runs/RUN_ID \
  -H 'X-Agent-Session-Token: ACCESS_TOKEN'
```

终态结构示例：

```json
{
  "schema_version": "1.0",
  "run_id": "...",
  "session_id": "...",
  "status": "completed",
  "result": {
    "status": "continue",
    "instruction": "点击右上角的加号",
    "target": {"left": 0.88, "top": 0.03, "right": 0.98, "bottom": 0.11},
    "confidence": 0.93
  },
  "error_code": null,
  "retryable": false
}
```

继续教程时，用新的 `client_turn_id` 和下一张截图再次创建 run。同一会话的同一 `client_turn_id` 返回原 run，不重复调用模型。可用 `DELETE /api/v1/agent/runs/{run_id}` 取消运行，用 `DELETE /api/v1/agent/sessions/{session_id}` 结束会话并销毁沙箱。

## 配置

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `GUOJING_DEEPSEEK_API_KEY` | 无 | staging/production 必填 |
| `GUOJING_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口 |
| `GUOJING_DEEPSEEK_VISION_MODEL` | `deepseek-v4-flash-vision-exp` | 可配置实验视觉模型 |
| `GUOJING_AGENT_RUN_TIMEOUT_SECONDS` | `90` | 整次 Agent run 超时 |
| `GUOJING_AGENT_MAX_CONCURRENCY` | `4` | 最大并发 run |
| `GUOJING_AGENT_QUEUE_CAPACITY` | `20` | 内存等待队列容量 |
| `GUOJING_AGENT_CONFIDENCE_THRESHOLD` | `0.70` | 返回可点击目标的最低置信度 |
| `GUOJING_SANDBOX_DOCKER_HOST` | Docker 环境默认值 | Docker Engine 地址 |
| `GUOJING_SANDBOX_IMAGE` | `python:3.12-slim` | 预拉取的沙箱镜像 |
| `GUOJING_SANDBOX_IDLE_TTL_SECONDS` | `600` | 空闲容器回收时间 |
| `GUOJING_DATABASE_URL` | `sqlite:///./data/guojing.db` | 元数据数据库 |

国内云生产部署建议把 API 与 Docker Worker 分离到受限 ECS，Docker API 只允许 API 服务访问，不暴露公网；镜像从国内仓库预拉取并锁定 digest。容器本身始终使用 `network=none`，且不能注入 DeepSeek、数据库或云服务凭据。

## 验证

默认测试不访问网络、不调用付费模型，也不要求 Docker：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
```

显式运行真实模型评测（会调用 DeepSeek 并要求 Docker 正常运行）：

```bash
GUOJING_RUN_DEEPSEEK_EVALUATION=1 uv run pytest -m integration \
  tests/evaluation/test_deepseek_integration.py
```

评测集包含 20 张确定性生成的手机界面，门槛为状态正确率至少 90%，目标框 IoU ≥ 0.5 的比例至少 80%。

Android 是下一阶段工作，不列入本阶段验收。实现原理和安全边界见 [Deep Agent 后端学习记录](docs/learning/59-deep-agent-backend.md)。

## 第二阶段

- 删除 Android 旧教程目录、状态图、静态执行引擎和手动截图流程。
- 接入 Android 11+ 无障碍截图、新会话/run/SSE API。
- 增加悬浮球、目标框、文字指引和系统 TTS。
- 接入阿里云 Fun-ASR；不改变本阶段定义的智能体协议。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
