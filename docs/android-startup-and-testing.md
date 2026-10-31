# Android 启动与测试

Android 最低 API 30，编译使用 SDK Platform 37、Build Tools 37.0.0、Gradle Wrapper 和已配置的 JDK 21 守护进程（Java 目标 17）。

```sh
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest
./gradlew connectedDebugAndroidTest
```

模拟器 Debug 默认连接 `http://10.0.2.2:8000`。真机推荐 USB `adb reverse` 配合 `-PGUOJING_DEBUG_API_BASE_URL=http://127.0.0.1:8000`，也可使用局域网 IP；连接、安装及逐项操作见 [Android 真机验证教程](android-real-device-validation.md)。生产签名包必须同时提供真实 HTTPS API 地址和四个签名环境变量，缺一会在 release 构建时失败：

```sh
export GUOJING_SIGNING_STORE_FILE=/安全目录/guojing.jks
export GUOJING_SIGNING_STORE_PASSWORD=...
export GUOJING_SIGNING_KEY_ALIAS=...
export GUOJING_SIGNING_KEY_PASSWORD=...
cd android
./gradlew assembleRelease -PGUOJING_API_BASE_URL=https://api.example.com
```

签名文件及凭据不能提交。`.jks`/`.keystore`、APK 和构建产物被 `.gitignore` 忽略；仍应检查暂存内容。发布签名、域名及适用的 App 备案由上线前提供。

## 首次操作

1. 安装与云端后端配套的新版 APK，打开“老牌子”，在设置页输入并保存邀请码。这一步仅在 Android Keystore 加密后的本机存储，不触发网络或截图。
2. 在系统设置中开启无障碍服务。打开目标应用，点击浮动“帮我”，输入目标并明确确认。
3. 客户端首先兑换或读取本机设备凭据，重新核对同一个目标窗口；通过后才隐藏悬浮层截图并上传。目标改变则提示重新开始。
4. 结果只提示一步，指引目标框不接收触摸操作。用户完成这一步后点击下一步，才重新截图。应用不执行触摸、点击或手势，也不遍历节点文字。
5. 上传前将 `client_turn_id` 持久化，再核对窗口和显示几何；发生变化即阻止上传。网络中断时优先查询原任务；找到后恢复监听或读取终态，不取消原任务、不重截。SSE 和轮询共用 150 秒上限；只有原任务已结束或不存在，且用户再次操作时，才允许新截图和新任务。

设备停用、授权过期、设备今日额度、全站今日额度与服务繁忙有各自提示。应用重装会清除 Keystore 中的本机秘密，需要重新邀请。进程重启可恢复尚在 24 小时内的会话或原任务；旧目标坐标不会直接用于当前屏幕。

会话实现拆为 `SessionReducer`（纯状态规则）、`RunRecovery`（只读任务恢复）和 `ConfirmedCapture`（一次用户动作对应一次截图），Controller 仍对原有 UI 端口公开不可变状态。迟到网络响应和本地写入必须通过会话代次、session/run 身份检查；结束后不能恢复旧框或朗读。窗口检查只使用包名、窗口 ID 与显示几何，不能证明同一窗口内所有内容都没有变化。

JVM 回归包含：原任务找回后零重复上传、超时后读取原结果、错误会话响应、结束期间迟到写入、同包窗口变化，以及保存请求编号期间切换窗口的上传阻断。运行记录与后端兼容性见 [第 65 模块](learning/65-bounded-guidance-workflow.md)。

## 状态引导首页

首页会按邀请码、指引服务、悬浮入口的准备情况突出下一步。邀请码已保存时显示“首次确认目标时激活”；“可以开始使用了”只表示本地准备完成，不会提前联网校验授权。打开需要帮助的应用后，仍从“帮我”确认目标再开始识别。

保存邀请码失败会保留输入，成功后清空并收起表单。草稿随 Activity 的 ViewModel 保留，可跨旋转使用；进程退出后未保存草稿不恢复。已有指引时不能更换邀请码，关闭悬浮入口前会确认同时结束当前指引。任务错误就近显示，详细使用说明可展开。

首页 Compose 测试覆盖普通字号、2 倍字号、320dp 窄屏及横向视口。`capture_home_previews_for_visual_review` 在测试应用私有 `files/` 中生成 `home-normal.png`、`home-large-font.png`，用于人工检查；截图、APK 和模拟器状态不提交仓库。完整实现说明见 [首页重构学习记录](learning/64-android-home-redesign.md)。

## 真机验收

本地真机功能验收可以使用 USB 连接的 Debug 包，步骤和记录模板见 [真机验证教程](android-real-device-validation.md)。首次配置的零请求检查应排除恢复旧会话的情形；日志只能辅助验证请求时机，截图边界需结合自动化测试和代码检查。

上线前在至少两台真实 Android 设备上确认：首次目标确认前零网络/零截图；目标窗口在输入面板关闭后变化会阻止截图；多轮指引完整显示与语音同步；断网期间不会自动重传图片，恢复后能查询原任务；系统栏偏移、旋转和跨应用切换使旧框消失；额度耗尽不会调用模型；3 人同时使用仍能得到明确结果。云端发布验收需要正式服务、签名 APK 和模型配置。
