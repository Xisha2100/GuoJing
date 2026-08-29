# 模块 23：教程检索与版本匹配

## 目标

把模块 22 的 `EvidenceEnvelope` 交给现有的确定性匹配规则，选择“当前包名下、页面锚点最匹配”的已发布教程节点。这里不让模型猜教程，也不因为找到一个相似文本就自动执行操作。

## 调用链

```text
EvidenceEnvelope
  -> AppIdentity + AnchorEvidence + structure_score
  -> TutorialService.list_published_for_package()
  -> match_screen() for every published graph/node
  -> assess_node_reuse()
  -> TutorialMatchDecision
```

`TutorialService.list_published_for_package()` 先读取轻量目录摘要，再按图 ID 加载当前发布修订。这样包名过滤仍由应用服务负责，Repository 不需要暴露 HTTP 或数据库细节；后续数据量变大时可以把过滤下推到 SQL 查询。

## 决策语义

- `matched / strong_match`：页面必需锚点和结构分数足够高，且节点在当前版本可复用。
- `uncertain / screen_evidence_uncertain`：有候选但缺少必需锚点或总分低，处理器应停在人工复核。
- `uncertain / version_requires_review`：页面看起来匹配，但 APP 版本变化且没有经过下一状态验证。
- `no_tutorial / no_published_tutorial`：该包没有已发布教程，可以转入模块 18 的基础指引。
- `no_tutorial / no_screen_match`：有该包教程，但没有一个节点与当前证据匹配。

候选排序使用匹配分数、是否强匹配、图 ID、节点 ID 四个键，最后两个键保证相同分数时结果仍然稳定可复现。返回值只含图/节点 ID、分数和兼容性评估，不含截图或 OCR 原文。

## 版本更新为什么默认停下

已有的 `assess_node_reuse()` 允许“同一已验证版本”的低风险节点继续尝试；版本改变时，即便当前页面匹配，也会返回 provisional。只有用户完成低风险操作并观察到预期下一状态，后续执行引擎才可以将它重新视为 verified。金融和不可逆操作始终要求人工复核。

这使“教程部分变了还能不能用”变成一个可测试的状态问题，而不是让 LLM 自行决定继续点击。

## Java/Python 对照

| Python | Java/Kotlin 对照 |
| --- | --- |
| `TutorialMatchDecision` | sealed result / sealed interface |
| `TutorialMatchStatus` | enum class |
| `max(..., key=...)` 稳定排序 | Comparator 链 |
| `TutorialService` | application service / use case |
| `match_screen`、`assess_node_reuse` | 纯函数 domain service |

## 测试重点

测试覆盖了强匹配、未知包、弱证据和新版本四条路径，并复用了模块 01 已有的页面匹配与版本兼容规则。下一模块会把这个决定接入 LangGraph-compatible 编排状态；编排层只能调用本服务，不能绕过它直接产生 Android 操作。
