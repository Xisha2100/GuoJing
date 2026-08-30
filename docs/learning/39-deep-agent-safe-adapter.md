# 模块 39：Deep Agent 安全适配器

`DeepAgentGuidanceModel` 不依赖 LangChain 包；它定义一个极小的 `DeepAgentInvoker` 端口，未来 SDK 实现只需适配 `invoke`。传入 agent 的只有任务、安全规则和输出 schema，没有 request UUID、问题、截图、OCR、Accessibility tree 或 Android 工具。

返回值仍会经过模块 31 的 action ID parser 与 catalog，因此 agent 无法自创文案或触发设备操作。此处的接口隔离类似 Java 的 anti-corruption layer：第三方 SDK 的对象不扩散到核心用例。
