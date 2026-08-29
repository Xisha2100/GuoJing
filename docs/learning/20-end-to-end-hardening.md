# 模块 20：端到端安全收口

## 1. 本模块做了什么

本模块把 16–19 的链路收口为可重试、可关联、可 fail-closed 的 MVP：

```text
Android 脱敏 → POST received
                    ↓
             metadata processor
              ↙             ↘
      human review       safe guidance
```

## 2. 幂等

`client_request_id` 现在作为一次提交的幂等键。网络请求已经到达服务端但客户端没有收到响应时，重复 POST 会复用原收据，而不是创建第二条结果。服务端只保留 UUID、路由和状态等元数据，不把幂等设计建立在保存原图上。

## 3. 响应关联

Android 查询状态时校验 URL 请求 ID 和响应 `request_id` 一致；ViewModel 继续校验客户端请求 ID、意图和处理路由与原始收据一致。服务器或代理返回错请求时，页面保持原状态并显示可重试错误。

## 4. 双端安全检查

服务端领域对象和 Android parser 都拒绝危险指引文字。OCR 隐私建议超过 20 项时不再静默截断，而是把状态标记为不可发送并提示用户重新选择更小范围的截图。

## 5. 验证范围

Python 测试覆盖重复提交、处理器分支、管理员权限、CSRF、人工发布和危险文案；Android JVM 覆盖错配响应和危险指引解析。设备测试继续覆盖真实提交页面。真实模型、跨进程队列、认证后的家属授权和图片尺寸深度解码仍属于下一阶段的生产化任务。

## 6. Java/Python 对照

幂等键相当于 Java 服务中唯一约束或 `Idempotency-Key` 表；这里先用受限内存映射实现 MVP。`Protocol` 相当于端口接口，`dataclass(frozen=True)` 相当于不可变 record。真正部署多 worker 时，内存映射必须替换为带 TTL 的共享存储。
