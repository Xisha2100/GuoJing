# 后端启动与测试

## 本地启动

使用 Python 3.12.13 和 uv。需有正在运行的 Docker Engine 和已经拉取的 `python:3.12-slim` 镜像。复制根目录 `.env.example` 为 `.env.local`，把 `GUOJING_DEEPSEEK_API_KEY` 替换为个人测试密钥；文件不入库。

```sh
uv sync
uv run alembic upgrade head
docker pull python:3.12-slim
uv run uvicorn guojing.main:app --reload
```

本地默认 `sqlite:///./data/guojing.db`，SQLite WAL 在迁移时开启。第二个连接同一数据库的 API 进程会因独占锁而拒绝启动。`GET /health` 只说明进程可响应；`GET /ready` 检查数据库、迁移、模型配置、Docker 镜像和处理协程，不调用模型。生产时须使用部署手册中的 rootless Docker、固定镜像 digest 与受限配置。

## 邀请及接口验证

```sh
uv run guojing-admin invite --label my-test-phone
uv run guojing-admin devices
uv run guojing-admin usage
```

Android 设置页保存邀请码时不联网；确认目标后才用本次安装 UUID 与客户端生成的随机秘密兑换设备。`POST /api/v1/devices/activate` 请求体字段为 `schema_version=1.0`、`invitation_code`、`installation_id`、`device_secret`。相同三元组可重复提交，返回同一设备；其他安装不能重用邀请码。开发时可用脚本生成 UUID 和秘密，且不得在 shell 历史或日志记录真实凭据。

所有 `/api/v1/agent/*` 请求需 `Authorization: Bearer <device_id>.<secret>`。已有会话的 run、GET、SSE、DELETE 还需 `X-Agent-Session-Token`。创建会话的请求示例：

```json
{"schema_version":"1.0","client_session_id":"11111111-1111-4111-8111-111111111111","goal":"帮我找到扫一扫","target_package":"com.tencent.mm"}
```

创建 run 仍使用 `client_turn_id`、`image_media_type`、`screen_width`、`screen_height`、`screenshot_base64`。图片接受 JPEG/PNG，解码后最多 8 MiB，单边最多 4096 像素；后端按实际接收的 HTTP 字节限制为 12 MiB。上传响应丢失时，用 `GET /api/v1/agent/sessions/{session_id}/turns/{client_turn_id}` 查原任务；重复提交相同编号不再执行模型。新的模型执行使用新编号。SSE `/api/v1/agent/runs/{run_id}/events` 与 `GET /api/v1/agent/runs/{run_id}` 返回同一状态。

邀请码兑换按 IP 限制每分钟 5 次，创建设备任务每分钟 6 次。单设备同时仅一个未完成任务。额度在入队时预留；开始模型调用前排队超时、取消或拒绝会退还。模型调用后即使失败也计一次。北京时间零点换日。实际成本还要结合每轮 token 汇总和模型价格估算。

## 检查命令

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
```

默认测试无需网络、模型或数据库服务。真实 Docker 隔离验收仅在明确允许创建短时测试容器时运行：

```sh
GUOJING_RUN_DOCKER_TESTS=1 uv run pytest -q tests/infrastructure/sandbox/test_docker_integration.py
```

付费模型评测使用合成数据，不上传真实用户截图：

```sh
GUOJING_RUN_DEEPSEEK_EVALUATION=1 uv run pytest -q tests/evaluation/test_deepseek_integration.py
```

评测门槛是状态正确率至少 90%，目标框 IoU≥0.5 的比例至少 80%；这项评测仍须在提供真实模型密钥后实际运行。

## 故障及恢复

`GET /ready` 返回 503 时，先在服务器本机看 `/internal/status` 与 `journalctl -u guojing`，然后检查数据库迁移版本、磁盘、rootless Docker socket、镜像和工作协程。清理容器失败时服务停止接受新分析；先排除 Docker 故障，再按部署手册重启服务清理同部署标签的遗留容器。备份只包含设备授权和每日用量；恢复后会话须重新开始，并用 `guojing-admin resume --reconciled` 人工解除暂停。
