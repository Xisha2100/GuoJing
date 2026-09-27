# Android 启动与测试

Android 最低 API 30，编译使用 SDK Platform 37、Build Tools 37.0.0、Gradle Wrapper 和已配置的 JDK 21 守护进程（Java 目标 17）。

```sh
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest
./gradlew connectedDebugAndroidTest
```

模拟器 Debug 默认连接 `http://10.0.2.2:8000`。真机调试可用 `-PGUOJING_DEBUG_API_BASE_URL=http://<局域网 IP>:8000`。生产签名包必须同时提供真实 HTTPS API 地址和四个签名环境变量，缺一会在 release 构建时失败：

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
5. 上传前将 `client_turn_id` 持久化，网络中断时优先查询原任务。SSE 和轮询共用 150 秒上限；断网不会自动重传截图。只有用户明确重试才创建新截图和新任务。

设备停用、授权过期、设备今日额度、全站今日额度与服务繁忙有各自提示。应用重装会清除 Keystore 中的本机秘密，需要重新邀请。进程重启可恢复尚在 24 小时内的会话或原任务；旧目标坐标不会直接用于当前屏幕。

## 真机验收

在至少两台真实 Android 设备上确认：目标确认前零网络/零截图；目标窗口在输入面板关闭后变化会阻止截图；多轮指引完整显示与语音同步；断网期间不会重传图片，恢复后能查回原任务；系统栏偏移、旋转和跨应用切换使旧框消失；额度耗尽不会调用模型；3 人同时使用仍能得到明确结果。上述真机与云端验证需要正式服务、签名 APK 和模型配置。
