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
2. 打开要操作的应用，无需返回老牌子选择应用。点击屏幕边缘的“帮我”。
3. 面板自动显示当前应用，输入目标并阅读截图上传说明，点击“开始指引”。取消输入不会创建会话或上传截图。
4. 面板和键盘收起后，应用确认原窗口仍在前台，再提交第一张截图。之后每点击一次“我已完成”才上传下一帧。
5. 返回 `continue` 时，页面上会出现目标框、箭头和单步文字，并自动朗读一次。手动完成操作后点击“我已完成”，再分析下一帧。
6. 可随时点击“重播”或“结束”。长文字随播报滚动，语音不可用时可以点击“查看后文”。切换应用时隐藏旧指引并保留“帮我”；确认新目标才结束旧会话。结束后悬浮入口仍保留。

应用进程被系统结束后，会话 token 可从 Android Keystore 加密存储恢复。为避免显示过期坐标，恢复后应重新截图确认当前页面。

## 验收检查

自动检查覆盖当前应用会话、跨应用替换、超时、坐标失效、完整文字分段、协议和显示器读取。默认测试不调用 DeepSeek；真实手机上的云端多轮会话仍按下列清单验收。

- 无障碍服务未连接时需先授权；悬浮输入取消或目标为空时不创建会话、不上传截图。
- 初次点击“开始指引”确认后提交第一帧；后续点击“我已完成”才提交下一帧。
- 截图中不包含老牌子的悬浮层。
- `continue` 只显示一个目标框；转屏或切换应用后旧框消失并要求重试。
- SSE 断开时客户端能通过 GET 恢复；失败时只展示可重试提示，不显示服务端原文。
- “结束”会立即移除悬浮层、清除本地会话，并请求取消当前 run、关闭后端会话；断网时远端清理为尽力执行，服务端过期机制仍生效。

如需运行设备 Compose 测试：

```fish
cd android
./gradlew connectedDebugAndroidTest
```
