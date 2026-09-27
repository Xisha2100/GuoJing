# 老牌子（GuoJing）

老牌子由 Python 后端与 Android 客户端组成。用户从当前应用的“帮我”悬浮入口确认目标，客户端才激活设备、截图并请求单步视觉指引；应用展示目标位置并朗读完整说明。无障碍服务不执行点击或手势，也不读取节点文字。

当前实现了受邀设备的杭州 ECS 单机试点所需的接口、配额、任务队列、客户端恢复、运维脚本和备份工具。云端、真实模型与真机验收尚需服务器、域名、证书、签名材料和模型密钥。旧教程、管理员系统、人工审核和 React 管理网页已经移除。

## 试点配置

| 项目 | 默认值与行为 |
|---|---|
| API | Python 3.12.13、一个 Uvicorn 进程；Nginx HTTPS，API 仅监听 127.0.0.1 |
| 数据 | SQLite WAL；会话创建满 24 小时失效，按分钟删除会话及关联文字 |
| 准入 | 最多 10 台受邀设备；邀请码单次使用、7 天有效；安装凭据 90 天有效 |
| 容量 | 2 个分析任务同时运行、8 个等待；排队 30 秒、分析 90 秒、清理 5 秒 |
| 额度 | 北京时间每日每设备 50 次、全站 300 次；模型调用开始后计一次 |
| 模型 | 默认 `deepseek-flash`；一轮主/子智能体合计最多 12 次、单次最多输出 2,048 tokens |
| 容器 | 每轮最多两个临时沙箱；无网络、只读根、0.5 CPU、512 MiB、64 PIDs |
| 恢复 | 授权与用量每 6 小时备份到杭州私有 OSS；备份保留 24 小时，恢复后暂停分析 |

部署参数和操作见 [杭州 ECS 部署手册](docs/deployment-aliyun-ecs.md)。首次发布使用空数据库；发布脚本会停入队、排空或终止在途任务、迁移并执行就绪检查。真实服务器规格从 2 核 4 GiB、60 GiB ESSD Entry、10 Mbps 峰值起步，按负载结果调整。

## 代码结构

```text
src/guojing/api/                  HTTP、SSE、认证前置与请求大小限制
src/guojing/application/agent/   任务、队列、模型调用预算
src/guojing/application/         设备准入与配额用例
src/guojing/domain/              无框架的状态与规则
src/guojing/infrastructure/      SQLite、Deep Agents、Docker 和进程锁
src/guojing/operations/          服务器命令、备份、监控与容器验收
android/app/                     Android 客户端
migrations/                      Alembic 历史迁移
deploy/                          ECS 初始化、发布、systemd、Nginx
tests/                           离线回归及显式启用的集成测试
```

领域层不导入 FastAPI、SQLAlchemy、Docker 或 Agent 框架。截图只在请求、可清零的队列缓冲及本轮容器中使用；数据库与备份均不存截图或完整模型消息。模型日志只汇总调用数、tokens、耗时及错误码。每轮重新创建和销毁沙箱，跨轮只从已完成的文字步骤恢复。

## 本地开发

需要 Python 3.12.13、uv 和 Docker Engine。把 [`.env.example`](.env.example) 复制为 `.env.local` 并填写本地模型密钥。调试客户端可用 Android 模拟器地址 `http://10.0.2.2:8000`；release 只接受真实 HTTPS 域名。

```sh
uv sync
uv run alembic upgrade head
docker pull python:3.12-slim
uv run uvicorn guojing.main:app --reload
```

本地调试也须先发邀请码、在客户端保存，并在目标确认后激活。`guojing-admin` 仅在服务器命令行提供，不开放管理 HTTP 接口：

```sh
uv run guojing-admin invite --label tester-1
uv run guojing-admin devices
uv run guojing-admin usage
```

接口契约：

- `POST /api/v1/devices/activate`：邀请码、安装 UUID、客户端随机秘密绑定本次安装；相同安装重试幂等。
- 所有 `/api/v1/agent` 请求都要 `Authorization: Bearer <device_id>.<secret>`；会话相关请求还要 `X-Agent-Session-Token`。查询、SSE 与取消同时检查设备所有权；停用后拒绝请求，后台任务在 15 秒内取消。
- `POST /api/v1/agent/sessions` 和 `POST /api/v1/agent/sessions/{session_id}/runs` 成功响应保留 `schema_version=1.0`。提交前保存 `client_turn_id`；响应丢失可用 `GET /api/v1/agent/sessions/{session_id}/turns/{client_turn_id}` 找回任务。重新执行必须用新的请求编号。
- `GET /health` 检查进程；`GET /ready` 检查数据库、迁移、Docker 镜像和后台处理器，不调用付费模型。`GET /internal/status` 仅本机访问，返回数字化队列及模型用量。

客户端设置页只在本机加密保存邀请码，确认目标之后才联网激活，再核对目标窗口才截图。断网时先查回原任务；不会自动重传截图。设备停用、设备和全站额度用尽、服务繁忙有明确提示。卸载重装需重新邀请。

## 验证

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
cd android && ./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest
cd android && ./gradlew connectedDebugAndroidTest
```

真实 Docker 检查需显式设置 `GUOJING_RUN_DOCKER_TESTS=1`。付费 DeepSeek 合成评测需显式设置 `GUOJING_RUN_DEEPSEEK_EVALUATION=1`，目标是状态正确率 ≥90%、目标框 IoU≥0.5 的比例 ≥80%。两台真机、多轮断网恢复、三人同时使用和先 3 人试用 48 小时均需在云端另行验收。

详细本地步骤见 [后端启动与测试指南](docs/startup-and-testing.md) 和 [Android 启动与测试指南](docs/android-startup-and-testing.md)。模块学习记录见 [后端](docs/learning/59-deep-agent-backend.md)、[Android](docs/learning/60-android-agent-client.md) 和 [试点部署](docs/learning/61-cloud-pilot.md)。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
