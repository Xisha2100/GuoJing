# 模块 25：模型适配器与安全降级

## 目标

把 LangGraph/Deep Agent 的模型调用限制在一个很小的端口：输入是已经丢弃图片后的请求元数据，输出是 JSON-like 的人工说明候选。模型不持有 `HelpRequestService`、Repository 或 Android 控制器，也不能改变处理状态。

## 输出契约

模型必须返回：

```json
{
  "title": "确认当前页面",
  "steps": [
    {
      "step_id": "look",
      "title": "看标题",
      "instruction": "请你亲自确认页面顶部的标题。",
      "requires_manual_action": true
    }
  ]
}
```

`StructuredGuidanceParser` 会拒绝未知字段、空字符串、超长内容、超过 20 步的列表和 `requires_manual_action != true` 的步骤，然后交给领域层再次检查支付、转账、密码、验证码、下单、账号删除等危险词。

## 安全降级

模型已经抛出的异常、JSON 解析失败或领域规则拒绝，都会变成统一的 `needs_human_review` 结果。当前同步端口还没有独立的调用 deadline；真实 provider 接入前必须补上连接/读取/总时限和可回收 processing lease。错误细节不直接暴露给老年用户，也不会因为重试而自动重复第三方 APP 操作。教程路由也被适配器拒绝，必须先由模块 23 完成证据和版本匹配。

## 与 LangGraph/Deep Agent 的接入点

未来可以写一个很薄的适配器：

```python
class DeepAgentGuidanceModel:
    def generate(self, context: ModelGuidanceContext) -> Mapping[str, object]:
        raw = agent.invoke({"request_id": str(context.request_id)})
        return raw
```

`SafeGuidanceModelProcessor` 仍然包在它外面，负责解析和降级。这样更换 Qwen、OpenAI-compatible API 或本地模型时，不会把供应商 SDK 传入 domain/application 代码。

## 为什么当前没有安装模型依赖

本阶段先验证状态机和安全合同，不让测试依赖模型 API Key、网络或付费额度。等确定模型服务、区域合规和预算后，再用 `uv add` 加入具体 SDK，并为真实适配器增加带桩的集成测试；纯领域测试继续离线运行。

## Java/Python 对照

| Python | Java/Kotlin 对照 |
| --- | --- |
| `GuidanceModel` Protocol | interface |
| `ModelGuidanceContext` frozen dataclass | Java record / Kotlin data class |
| `Mapping[str, object]` | `Map<String, Any>`（建议再用 DTO 收窄） |
| parser + domain validation | Jackson/kotlinx serialization + Bean Validation |
| review fallback | sealed error/result branch |

模块 21–25 至此形成一条可离线测试的组件链路：持久化结果 → 受控证据 → 教程匹配 → 编排状态 → 模型候选校验。模块 27 才把确定性工作流接到生产 composition root；真正接入模型时，仍必须沿用这五层边界，并补上任务相关上下文、超时和风险 allowlist。
