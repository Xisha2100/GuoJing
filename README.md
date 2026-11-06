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
| 模型 | 默认 `deepseek-flash`；每轮最多 12 次、单次最多输出 2,048 tokens；新双阶段链路正常 2 次、最多 4 次 |
| 引擎 | 默认 `legacy_hardened`，通过 `GUOJING_GUIDANCE_ENGINE=bounded` 显式选择新链路 |
| 容器 | 旧链路每轮一个、全站最多两个临时沙箱；无网络、只读根、0.5 CPU、512 MiB、64 PIDs；新链路无需 Docker |
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

领域层不导入 FastAPI、SQLAlchemy、Docker 或 Agent 框架。截图仅用于本轮请求和内存处理；旧链路另写入本轮临时沙箱。数据库与备份均不存截图或完整模型消息，所有路径关闭 tracing、自动文件卸载和模型摘要。队列与 Android 图片缓冲尽力清零；Python Base64 等不可变副本无法保证物理擦除。跨轮只传递最近 6 条完整文字指引，序列化历史上限 4,000 字符，且不将历史指引当作已执行事实。

## DeepAgents 调用链

后端使用 DeepAgents **0.7.32**（依赖范围 `>=0.7.32,<0.8`，完整解析结果见 `uv.lock`），提供两种保持同一 HTTP 协议的实现：

- `legacy_hardened`：主模型按固定顺序委派视觉分析和文本审校，成功路径 5 次调用。执行前限制工具与委派顺序，审校必须绑定同一候选，最终输出不得改写已审校内容；否决直接返回无法判断。
- `bounded`：代码依次调用视觉候选和独立视觉复核，两者使用同一张当前截图。正常 2 次调用；仅有视觉证据的措辞问题允许修订一次并再次复核，最多 4 次。无效结构、审校否决或不确定风险返回现有 `cannot_determine`，不隐式重试或切回旧引擎。该模式不创建 Docker 连接、容器或图片文件。

两个实现只开放本阶段允许的工具，拒绝文件、命令及额外委派；保留每轮 12 次共同预算、90 秒运行上限及既有配额。候选、风险、审校标识与版本只供内部校验，不加入 `schema_version=1.0` 响应。日志包含阶段调用数、tokens、耗时、引擎/提示词版本和固定拒绝代码，不包含模型正文。

实现与验证见 [受限视觉工作流与会话恢复](docs/learning/65-bounded-guidance-workflow.md)，设计依据见 [重构方案](docs/deepagents-refactor-plan-2026-10-31.md)。默认保留加固旧链路，待真实模型对照与试点验收后再切换。旧链路 fork 子智能体仍属于上游 beta API。

## 本地开发

需要 Python 3.12.13 和 uv；默认旧链路还需要 Docker Engine。把 [`.env.example`](.env.example) 复制为 `.env.local` 并填写本地模型密钥；评估新链路时设置 `GUOJING_GUIDANCE_ENGINE=bounded`，可跳过 Docker 拉取。调试客户端可用 Android 模拟器地址 `http://10.0.2.2:8000`；release 只接受真实 HTTPS 域名。

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
- `GET /health` 检查进程；`GET /ready` 检查数据库、迁移、模型配置和后台处理器，旧链路另检查 Docker 镜像，不调用付费模型。`GET /internal/status` 仅本机访问，返回既有数字化队列及模型用量。

Android 首页采用暖白朱红的状态引导布局：未配置时突出下一项准备工作，已准备好时显示使用方法，有会话时优先展示当前任务。邀请码保存失败保留输入，成功才清空并折叠；会话中关闭悬浮入口需要确认结束。

客户端设置页只在本机加密保存邀请码，确认目标之后才联网激活，再核对目标窗口才截图。断网时先查回原任务；找到后恢复监听，不取消原任务或再次截图。恢复旧结果不会重放目标框。会话代次及 run/session 身份校验阻止迟到结果写回、展示或朗读；截图前后、上传前和显示前核对窗口及显示几何。设备停用、设备和全站额度用尽、服务繁忙有明确提示。卸载重装需重新邀请。

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

真实 Docker 检查需显式设置 `GUOJING_RUN_DOCKER_TESTS=1`。付费 DeepSeek 合成评测需显式设置 `GUOJING_RUN_DEEPSEEK_EVALUATION=1`，通过 `GUOJING_GUIDANCE_ENGINE` 选择被测实现，目标是状态正确率 ≥90%、目标框 IoU≥0.5 的比例 ≥80%。现有合成集不能代替方案要求的复杂页面、拒绝、完成及多轮留出集。两台真机、多轮断网恢复、三人同时使用和先 3 人试用 48 小时均需另行验收。

详细本地步骤见 [后端启动与测试指南](docs/startup-and-testing.md)、[Android 启动与测试指南](docs/android-startup-and-testing.md) 和 [Android 真机验证教程](docs/android-real-device-validation.md)。真机教程从 USB 连接、构建安装和邀请码配置开始，覆盖新版首页、完整指引、断网恢复与大字体检查。模块学习记录见 [后端](docs/learning/59-deep-agent-backend.md)、[Android](docs/learning/60-android-agent-client.md)、[试点部署](docs/learning/61-cloud-pilot.md) 和 [Android 首页重构](docs/learning/64-android-home-redesign.md)。

支线研究：[Jev 图像与 Box 接入评估](docs/learning/62-jev-vision-evaluation.md)（2026-10-16）。建议先验证“视觉模型生成候选 + Jev 定位及核验”的混合方案；当前仅完成资料、代码和离线兼容性评估，尚未接入默认链路或取得真实模型效果数据。

项目审计：[项目说明与代码审计](docs/project-audit-2026-11-06.md)（2026-11-06）涵盖架构、接口、数据、部署、验证证据及整改条件。原 2 项 P1、6 项 P2 已修复并补充回归：后端 178 项、Android JVM 71 项、Pixel_7 设备测试 13 项通过。真实模型、Docker 和厂商设备场景仍须现场验收。模块记录见 [66 · 项目审计](docs/learning/66-project-audit.md) 和 [67 · 审计问题修复](docs/learning/67-audit-remediation.md)。

当前创建会话限制为每设备每分钟 6 次、最多 100 条未过期会话（已关闭也计数，默认保留 24 小时）；拒绝返回 429 和重试提示。数据库阻塞操作最多并发 4 个，SQLite 锁超时返回 503 `service_busy`。监控观察到接入连续暂停超过 10 分钟时告警，恢复后清除计时。

## License

本项目使用 [GNU General Public License v3.0](LICENSE)。
