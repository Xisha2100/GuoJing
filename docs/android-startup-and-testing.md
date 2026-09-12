# Android 启动与测试指南（Fish）

## 环境

Gradle 守护进程使用仓库配置的 JDK 21（Java 编译目标为 17），并需要 Android SDK Platform 37、Build Tools 37.0.0，以及正在运行的 Deep Agent 后端。Android 最低支持 Android 11（API 30）。所有命令均使用仓库内 Gradle Wrapper，不需要全局安装 Gradle。

```fish
cd android
./gradlew testDebugUnitTest
./gradlew lintDebug
./gradlew assembleDebug assembleDebugAndroidTest
```

## 配置后端地址并安装

Android Studio 模拟器访问宿主机时，debug 默认地址已经是 `http://10.0.2.2:8000`：

```fish
cd android
./gradlew installDebug
```

真机需要使用电脑在局域网中的地址；手机与电脑必须互通，后端也需要监听该网卡。示例：

```fish
cd android
./gradlew installDebug -PGUOJING_DEBUG_API_BASE_URL=http://192.168.1.20:8000
```

连接云端 HTTPS 后端时：

```fish
cd android
./gradlew installDebug -PGUOJING_DEBUG_API_BASE_URL=https://agent.example.com
```

release 构建必须配置 HTTPS 地址：

```fish
cd android
./gradlew assembleRelease -PGUOJING_API_BASE_URL=https://agent.example.com
```

不要把 DeepSeek、数据库或云服务密钥写入 Gradle 属性或 APK。Android 只需要后端 URL。

## 首次操作

1. 打开“老牌子”，点击“去开启”，在系统无障碍设置中启用“老牌子界面指引”。系统会明确提示该服务具备读取屏幕/截图能力。
2. 返回应用，选择要操作的目标应用，输入目标，例如“帮我找到微信扫一扫”。
3. 阅读并勾选逐帧上传说明，点击“开始指引”。应用会创建安全会话并打开目标应用。
4. 点击屏幕上的“开始识别”悬浮胶囊。该点击代表只上传当前这一帧；等待智能体返回。
5. 返回 `continue` 时，页面上会出现目标框、箭头和单步文字，并自动朗读一次。手动完成操作后点击“我已完成”，再分析下一帧。
6. 可随时点击“重播”或“结束”。切换到非目标应用时，悬浮层会自动隐藏。

应用进程被系统结束后，会话 token 可从 Android Keystore 加密存储恢复。为避免显示过期坐标，恢复后应重新截图确认当前页面。

## 验收检查

当前自动检查已通过：15 项 Android JVM 测试、Pixel_7（Android 16）上的 2 项 Compose 测试和 1 项截图显示器回归测试、lint（0 错误）以及应用/测试 APK 构建。模拟器启动布局已检查。上述测试不调用 DeepSeek；真实手机上的无障碍截图、跨应用悬浮框和云端多轮会话仍按下列清单验收。

- 未勾选上传说明或无障碍服务未连接时，“开始指引”不可用。
- 创建会话、自动打开目标应用不会自动截图；只有点击悬浮胶囊才会上传。
- 截图中不包含老牌子的悬浮层。
- `continue` 只显示一个目标框；转屏或切换应用后旧框消失并要求重试。
- SSE 断开时客户端能通过 GET 恢复；失败时只展示可重试提示，不显示服务端原文。
- “结束”会立即移除悬浮层、清除本地会话，并请求取消当前 run、关闭后端会话；断网时远端清理为尽力执行，服务端过期机制仍生效。

如需运行设备 Compose 测试：

```fish
cd android
./gradlew connectedDebugAndroidTest
```
