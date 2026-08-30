# 模块 31：审核动作目录与风险授权

## 问题

词表能够拦住“支付”这样的明显文字，但无法证明“把一千元打给对方”或英文改写同样危险。模型输出即使声明“由用户亲自操作”，也不应被授权解释金融或不可逆动作。

## 方案

模型现在只能返回稳定的 `action_ids`，例如 `general.observe_page`。`GuidanceActionCatalog` 在服务端将 ID 解析为审核过的标题和说明；未知 ID、重复 ID 或不在目录中的自由文本都会转人工复核。

风险由 `RiskLevel` 决定：

| 风险 | 授权结果 |
| --- | --- |
| `low` | 可生成自动说明 |
| `sensitive` | 停下并要求用户确认 |
| `financial` / `irreversible` | 必须人工复核 |

这个判断不读取 instruction 文字，因此把金融操作伪装成普通标题也不会被自动授权。

## 调用链

```text
模型 {"action_ids":[...]}
  -> ApprovedActionReferenceParser
  -> GuidanceActionCatalog
  -> RiskLevel 授权
  -> HelpRequestGuidance 或 needs_human_review
```

`ApprovedGuidanceAction` 是 Python 的不可变值对象，对应 Java 的 `record`；catalog 的作用类似后端中的受控权限表。模型只是在“申请使用一个能力”，不会拥有能力本身。

## 验证

测试覆盖未知 ID、重复 ID、自由文本输出，以及即使说明文字看起来无害、但风险标记为 financial 时仍被拒绝的情况。模块 34 会把同一机制扩展到已发布教程的 `transition_id`。
