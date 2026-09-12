# Android 智能体客户端

## 完成的闭环

客户端不再下载静态教程。用户在主界面选择一个可启动应用、填写目标并确认逐帧上传说明后，客户端创建 `/api/v1/agent/sessions` 会话并打开目标应用。之后只有用户点击悬浮胶囊时才会截图和创建 run；客户端优先监听 SSE，断流后使用 GET 指数退避恢复终态。

`continue` 结果包含归一化目标矩形。全屏 `TYPE_ACCESSIBILITY_OVERLAY` 只负责绘制非触摸的矩形、箭头和说明卡；独立的小窗口提供“开始识别/我已完成”“重播”和“结束”。下一张截图前会先隐藏两个窗口，避免把指引本身发送给模型。客户端从不调用无障碍节点动作，也不派发手势。

## 权限与隐私边界

- 最低 Android 版本为 11（API 30），截图使用 `AccessibilityService.takeScreenshot()`。
- 无障碍配置声明 `canTakeScreenshot=true`，但每次截图仍由用户主动点击触发。
- JPEG 长边最多 1440 像素、编码后最多 8 MiB；上传完成或失败后尽力清零持有的字节数组。
- 截图、Base64 和响应原文不写入日志或持久存储。
- 会话 token 与恢复状态使用 Android Keystore AES-GCM 加密；损坏或超过 24 小时的状态会被清除。
- release API 默认只允许配置 HTTPS 地址；开发 cleartext 例外仅位于 `src/debug` Manifest。
- 切出目标包时两个悬浮窗口自动隐藏。若屏幕尺寸或旋转在模型返回前变化，坐标结果不会展示，而是要求重新识别。

## 可测试边界

协议解析使用精确字段集合和固定 `schema_version=1.0`，未知枚举、非法坐标、终态携带目标框以及低于 0.70 的 `continue` 都会失败关闭。`AgentSessionController` 只依赖 repository、截图、悬浮层、TTS、会话存储和应用启动端口，因此 JVM 测试无需 Android 运行时或网络即可证明“创建会话不会自动截图”和“截图字节最终清零”。

## 截图方向读取回归修复

模拟器中目标应用已经打开时，截图仍可能被统一错误提示显示为“请先打开目标应用”。原因是后台服务调用 `Context.display` 读取旋转方向会抛出 `UnsupportedOperationException`。现在使用 `DisplayManager.getDisplay(Display.DEFAULT_DISPLAY)`，与截图使用同一个显示器；显示器不可用时失败关闭，不猜测旋转方向。方向读取放在获取截图缓冲区之前，避免读取失败导致缓冲区未关闭。

新增设备回归测试，使用未绑定显示器的应用上下文验证方向读取；旧实现已在 Pixel_7 模拟器复现异常。

## 尚未实现

目标输入目前是键盘文本。后续 Fun-ASR 应作为独立输入适配层接入，并从后端取得短期凭据；它不应改变视觉智能体 API，也不能把长期阿里云密钥放进 APK。
