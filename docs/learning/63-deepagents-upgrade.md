# 63 · DeepAgents 0.7.32 升级与调用链重构

历史记录：本文描述 2026-10-26 的升级状态。2026-10-31 后续重构已关闭工具默认权限、将否决改为阻断并绑定候选，新增可选双阶段视觉链路；当前实现见[第 65 模块](65-bounded-guidance-workflow.md)。

## 版本与范围

2026-10-26 查询 [PyPI 官方元数据](https://pypi.org/pypi/deepagents/json)，最新稳定版本为 0.7.32。项目原锁定版本为 0.7.13，声明下限为 0.7.10；本次使用 `uv add 'deepagents>=0.7.32,<0.8' --upgrade-package deepagents` 更新声明及锁文件。LangChain、LangChain Core、LangGraph、LangSmith 等依赖按新版本约束同步解析，完整版本以 `uv.lock` 为准。

本模块覆盖后端 DeepAgent 调用链及应用层接口，不改变 Android HTTP 协议、数据库结构、设备准入或用户确认后才能截图的规则。无新增环境变量。

## 职责划分

- `application/agent/ports.py` 定义只携带沙箱身份的 `SandboxHandle`，应用用例不再导入 DeepAgents；基础设施在边界处恢复具体后端类型，生产组合根仍提供 Docker 后端。
- `infrastructure/agents/deep_guidance_agent.py` 负责模型配置、截图上传、每轮图构造、调用预算回调和领域结果转换。
- `outputs.py` 集中定义主智能体、视觉分析、审校的结构化输出及坐标校验。
- `prompts.py` 集中管理角色提示词和语言规则。
- `validation.py` 校验子智能体调用及对应返回，防止把仅发出调用、错误响应或缺失结果当作成功执行。

## 行为修正

JPEG 与 PNG 分别写入 `.jpg`、`.png` 路径；不支持的媒体类型在上传前拒绝。上传返回必须恰好一项，路径吻合且没有错误，才构建模型图。

子智能体必须按 `ui-analyst` → `guidance-reviewer` 顺序各完成一次。通过工具调用 ID 关联结果，拒绝并行未完成调用、重复 ID、重复结果、错误状态和不符合对应结构的 JSON。审校的 `approved=false` 仍允许主智能体按照反馈修正候选，保留现有产品语义；这里验证流程完成与结果结构，不声称独立验证了修正后的语义正确性。

继续保留低置信度和语言违规时返回 `cannot_determine`、禁止 LangSmith tracing、每轮创建图且不使用 checkpointer 等约束。

## 新版 API 的实际限制

0.7.32 的 `create_deep_agent` 没有实例级 harness profile 参数；禁用隐式 `general-purpose` 仍需使用公开的 `register_harness_profile`，按完整 `openai:<model>` 键缓存注册，不能声称已移除该全局行为。注册会作用于进程内同名模型。没有引入私有 API 覆盖或暂时修改/恢复全局注册表的并发风险。

`mode="fork"` 仍是上游 beta 功能。因此新增测试运行实际安装的 DeepAgents/LangGraph 图，只替换模型生成结果，不 mock 图构建函数。测试验证视觉分析继承图片、审校只接收文本、两个固定子智能体可用、隐式通用子智能体不在可用列表、结构化输出闭环、5 次模型调用记账及 tracing 关闭。测试使用临时文件后端，不访问模型网络或 Docker。

## 验证

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
git diff --check
```

另外添加异常上传、未完成/失败/重复/乱序子智能体结果的回归测试。真实模型质量及 Docker 集成仍需显式启用既有集成测试；离线通过不能替代真实模型效果验收。本次未修改 Android，无需新增设备交互或布局验收。
