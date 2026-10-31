# Android 真机验证教程

适用于当前“暖白朱红”首页与“帮我”悬浮指引流程。建议先用一台 Android 11 或更高版本的测试手机，通过 USB 连接这台 Mac 跑通，再换另一品牌手机复测。首次准备约需 30～60 分钟。

本教程提供可执行步骤与验收标准，**不代表真机验证已经完成**。现有自动化及模拟器结果见 [首页重构学习记录](learning/64-android-home-redesign.md)。

## 1. 选择本次验证范围

| 范围 | 需要什么 | 能验证什么 |
| --- | --- | --- |
| 只看首页 | 手机、USB 线、Android 构建环境 | 配色、字号、滚动、表单、无障碍服务连接、入口开关 |
| 完整指引，推荐 | 上述条件，加上本地后端、Docker、真实模型配置和邀请码 | 首次激活、截图识别、多轮指引、错误与恢复 |
| 上线前验收 | 正式 HTTPS 服务、release 签名包、至少两台手机 | 真机兼容性、云端部署、多人并发和试用表现 |

仅检查首页时可先做第 2、4、5、8 节，不用启动模型服务；没有真实邀请码时，先完成首次配置页面和格式错误检查。完整指引会把测试应用截图发送到后端及配置的模型服务，并产生实际模型用量，请使用不含聊天、账户或个人资料的测试页面。

下列电脑命令以 macOS 为例。除注明“手机操作”外，都在终端执行。默认项目目录为 `/Users/xisha/Developer/AI_Projects/GuoJing`。

## 2. 连接手机

1. 手机打开开发者选项，开启“USB 调试”，用支持数据传输的 USB 线连接电脑。
2. 解锁手机，接受“允许 USB 调试”的电脑授权。具体菜单路径因品牌不同；连接方法参见 [Android 官方真机调试指南](https://developer.android.com/studio/run/device)。
3. 在终端 A 设置本次会话环境。若 Android Studio 或 SDK 安装位置不同，调整相应路径：

```sh
cd /Users/xisha/Developer/AI_Projects/GuoJing
export JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home'
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$ANDROID_HOME/platform-tools:$PATH"
adb devices -l
```

找到状态为 `device` 的真实手机，将序列号填到下面变量中；后续命令始终指定它，避免操作到模拟器或另一台手机：

```sh
export GUOJING_TEST_SERIAL='替换为手机序列号'
adb -s "$GUOJING_TEST_SERIAL" shell getprop ro.build.version.release
```

`unauthorized` 表示尚未在手机接受授权；空列表通常需要检查线缆、USB 模式或调试开关。`adb` 的设备选择及安装参数参见 [官方 adb 文档](https://developer.android.com/tools/adb)。

构建还需要 Android SDK Platform 37、Build Tools 37.0.0 和项目配置的 JDK 21 Gradle 守护进程。通过 Android Studio 的 SDK Manager 准备 SDK；使用仓库内 Wrapper，无需全局安装 Gradle。手机本身只需 Android 11 或以上。

## 3. 启动后端并生成邀请码

只看首页可跳过本节。完整验证需要 Python 3.12.13、uv，以及已启动的 Docker Engine。

在终端 B 进入项目根目录。仅当 `.env.local` 不存在时，复制示例配置：

```sh
cd /Users/xisha/Developer/AI_Projects/GuoJing
if [ ! -f .env.local ]; then
  cp .env.example .env.local
fi
```

用编辑器填写 `.env.local` 中的 `GUOJING_DEEPSEEK_API_KEY`，按账号实际可用的视觉模型核对 `GUOJING_DEEPSEEK_VISION_MODEL` 与 `GUOJING_DEEPSEEK_BASE_URL`。不要把密钥粘贴到命令、截图或测试记录中。已有配置应保留，不能用示例覆盖。

```sh
uv sync
uv run alembic upgrade head
docker pull python:3.12-slim
uv run uvicorn guojing.main:app --host 127.0.0.1 --port 8000
```

让终端 B 持续运行。若已有同一数据库的 API 服务，使用现有服务，不启动第二个进程。

回到终端 A 检查：

```sh
curl --fail --show-error http://127.0.0.1:8000/health
curl --fail --show-error http://127.0.0.1:8000/ready
uv run guojing-admin invite --label "真机验收手机A"
```

预期依次返回 `{"status":"ok"}`、`{"status":"ready"}` 和邀请码。`/ready` 检查本地依赖，不实际调用模型，不能证明密钥可用、余额充足或模型具备图像能力；这些由首次真实识别确认。

邀请码用于本次手机安装，不要公开或重复发给另一台手机。卸载或清除应用数据后需要新的邀请。保留终端 B 的访问日志，稍后用于检查请求时机；不要启用请求体或凭据日志。

## 4. 构建并安装 USB 调试包

在终端 A 建立手机到电脑的端口映射：

```sh
adb -s "$GUOJING_TEST_SERIAL" reverse tcp:8000 tcp:8000
adb -s "$GUOJING_TEST_SERIAL" reverse --list
```

然后构建。命令用子 shell 进入 `android/`，结束后终端仍在项目根目录：

```sh
(
  cd android
  ./gradlew assembleDebug -PGUOJING_DEBUG_API_BASE_URL=http://127.0.0.1:8000
)
adb -s "$GUOJING_TEST_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
adb -s "$GUOJING_TEST_SERIAL" shell am start -n com.xisha.guojing/.MainActivity
```

手机上打开的应用名称是 **“老牌子”**。`install -r` 在签名相同的情况下保留已有数据；若已经配置过应用，首页不会自动回到首次安装状态。首次配置验收最好使用没有安装过本应用的测试手机。

如需运行第 9 节自动化，先完成它，再进行第 5 节手工配置，避免测试卸载影响已经激活的应用数据。

这里的 `127.0.0.1:8000` 通过 USB 映射到电脑。项目默认的 `10.0.2.2` 仅用于 Android 模拟器，不能直接用于真机。API 地址在构建时写入，改地址后必须重新构建和安装。

完整验证前，可在手机浏览器访问 `http://127.0.0.1:8000/health`，应显示 `ok`。完成后关闭浏览器页面，再开始观察应用请求，避免把浏览器请求当作客户端请求。USB 线断开或手机重启后，重新执行 `adb reverse`。

## 5. 首次配置与首页验收

以下步骤按“没有恢复中的旧会话”的状态执行。如果手机已有会话，先在首页“结束本次指引”；旧会话恢复可能查询原任务，不能用它作为首次启动零请求的测试前提。

| 操作 | 预期结果 |
| --- | --- |
| 首次打开首页 | 暖白背景、朱红重点按钮；突出“先保存你的邀请码”，准备事项按顺序排列 |
| 输入部分邀请码，旋转手机再返回竖屏 | 未提交草稿仍在；输入框使用掩码，不展示明文邀请码 |
| 输入 `abc` 并点“保存邀请码” | 表单旁提示格式不正确，输入保留，仍可修改；不要用断网模拟保存失败，保存本来就在本机完成 |
| 换成第 3 节生成的真实邀请码并保存 | 成功后清空并收起表单，显示“邀请码已保存”和“更换邀请码”；此时尚未在线验证或激活 |
| 点“去开启指引服务” | 进入系统无障碍设置，找到“老牌子界面指引”并开启；返回首页显示服务“已连接” |
| 如果“悬浮入口”关闭，将它打开 | 首页显示“可以开始使用了”，提示去需要帮助的应用点击屏幕边缘的“帮我” |
| 展开、收起“查看详细使用说明” | 长文自然换行，页面能滚到底；截图上传说明不依赖详细说明展开，向下滚动仍可找到 |

悬浮入口默认已打开，因此首次开启服务后可能直接就绪；首页会跳过已完成事项，不必重复关闭再打开。应用使用无障碍悬浮层，无需另行寻找普通的“显示在其他应用上层”授权。

在以上步骤以及目标输入后取消的过程中，后端日志不应出现由本次操作发起的激活、建会话或上传任务请求。保存中的禁用重复提交、本机存储异常等路径不易稳定手工触发，交由已有 JVM/Compose 测试验证。

## 6. 跑通一次完整指引

1. **手机操作：**打开一个不含个人资料的测试应用页面，例如系统“设置”首页，目标填写“帮我找到显示或字体大小的入口，不修改设置”。避免支付、删除或修改账户等操作。
2. 点击屏幕边缘的 **“帮我”**。应看到“你想完成什么？”，以及目标应用和截图上传说明。
3. 先留空尝试开始，应提示输入目标；再输入目标并点“取消”。这两次都不应产生新任务或截图上传。
4. 重新点击“帮我”，填写目标，点击 **“开始指引”**。这一步才授权激活、创建会话和首次截图识别；首次成功路径通常不需额外点击“开始识别”。
5. 等待指引，检查目标框位置与文字说明是否对应当前页面，语音是否可听清。完整说明应能阅读和滚动；有“重播”或“查看后文”时检查其效果。
6. **由你自己操作手机**完成这一步，再点击 **“我已完成”**，进入下一次截图和识别。首页说明里的“下一步”在悬浮控制中对应这个按钮。等待期间不要连续提交。
7. 完成两三轮后，回首页查看任务状态，再点“结束本次指引”。应用应退出本次会话，不继续识别。

等待状态可能较短，不要求每个中间标题肉眼都能捕捉。真正需要确认的是：提示与当前阶段一致，等待或失败时不展示上一轮的旧指令，错误可读，操作有明确结果。

记录两类证据：手机上的状态/指引，以及终端 B 中 `/api/v1/devices/activate`、`/api/v1/agent/sessions`、任务提交和查询的时间。可在电脑查询用量：

```sh
uv run guojing-admin devices
uv run guojing-admin usage
curl --fail --show-error http://127.0.0.1:8000/internal/status
```

`/internal/status` 只供服务本机检查。其 `model_calls` 在任务结束时汇总本进程内主模型与子智能体的调用次数，不是截图数，也不是实时任务数；多用户共用服务时不能直接归因到这台手机。访问日志及计数能辅助检查联网和任务触发，**不能单独证明设备从未在内存截图**；严格的截图边界还要结合控制器/截图端口测试和代码审查。

## 7. 关键异常与会话限制

### 7.1 目标变化、服务断开、关闭确认

| 操作 | 预期结果 |
| --- | --- |
| 显示指引后切到另一应用 | 原目标框消失、语音停止；另一应用可能仍有全局“帮我”，这是正常行为 |
| 返回原目标应用 | 不能复用旧坐标；按当前提示点“开始识别”重新获取当前画面 |
| 显示指引后旋转屏幕 | 旧目标框消失；下一轮必须基于新方向重新识别，位置不能沿用旧屏幕 |
| 输入目标时切换到另一应用，再尝试确认 | 目标窗口校验失败，提示应用已切换/重新开始，不向新应用套用原目标 |
| 系统设置关闭“老牌子界面指引”，再回首页 | 服务显示“待开启”并提供设置入口；不能把服务断开显示成邀请码失效；重新开启后可继续准备 |
| 有会话时回首页尝试更换邀请码 | 入口禁用，并说明“请先结束当前指引，再更换邀请码” |
| 有会话时关闭“悬浮入口”，先取消 | 出现结束确认；取消后保留会话及入口开关 |
| 再次关闭并选择“关闭并结束指引” | 会话结束，悬浮入口关闭；没有会话时再次切换则不需要确认 |

### 7.2 USB 模式下模拟断网

USB 映射连接不依赖手机 Wi-Fi，单关 Wi-Fi 不能验证本教程的断网路径。在终端 A 移除当前映射：

```sh
adb -s "$GUOJING_TEST_SERIAL" reverse --remove tcp:8000
```

先在**已经成功开通过的测试手机**上、尚未开始新会话时执行，再从目标应用确认一次目标。预期显示连接失败，设备开通状态仍保留。恢复连接后重新点“帮我”并输入目标：

```sh
adb -s "$GUOJING_TEST_SERIAL" reverse tcp:8000 tcp:8000
```

再测一次任务中断：等后端日志已经收到一轮任务提交、手机仍在等待识别时，移除映射，稍后恢复。若结果返回太快，记录为“未覆盖该时序”，不要把正常结束当成断网恢复通过。

预期行为：

- 已有任务优先查询原任务，SSE 失败可回退轮询；整体等待上限约 150 秒，恢复网络不保证立即有结果。
- 移除映射不能保证已经建立的长连接立即断开，应结合后续请求失败和手机状态判断是否真的覆盖了断网。
- 没有新的用户操作时，不应自动重复提交截图任务；查询请求重复出现是正常恢复行为。
- 超时或失败后若显示 **“重新识别”**，需用户明确点击才重新截图并提交新任务。建会话前失败则重新从“帮我”开始。
- 错误应在相应提示区域或已有会话的任务卡内显示；临时连接错误不能把“已开通”改成“未开通”。

可额外测试应用进程重启：先记录当前阶段，再重启手机并恢复 USB 映射、检查服务是否重新连接。24 小时内仍有效的会话可尝试恢复，处理中查询原任务；旧坐标不能直接恢复使用。未保存的邀请码草稿只保证旋转时保留，不保证进程退出或手机重启后保留。

## 8. 字体、横屏与窄屏

先在普通字号检查首页、邀请码错误、使用说明、目标输入面板、任务卡和关闭确认框，再开系统自动旋转，在横屏重复检查。重点看：文字能读完、页面能滚动、键盘不挡住唯一操作、按钮可触达、没有重叠或截断。

精确测试 2 倍字体时，在终端 A **先记录原设置**，保持该终端打开：

```sh
GUOJING_ORIGINAL_FONT_SCALE="$(adb -s "$GUOJING_TEST_SERIAL" shell settings get system font_scale | tr -d '\r')"
adb -s "$GUOJING_TEST_SERIAL" shell settings put system font_scale 2.0
```

重新打开首页并完成上述检查。检查完立即恢复原值：

```sh
if [ "$GUOJING_ORIGINAL_FONT_SCALE" = "null" ]; then
  adb -s "$GUOJING_TEST_SERIAL" shell settings delete system font_scale
else
  adb -s "$GUOJING_TEST_SERIAL" shell settings put system font_scale "$GUOJING_ORIGINAL_FONT_SCALE"
fi
```

部分厂商系统可能限制 ADB 修改字体，此时使用系统“字体大小”设置，并记录实际档位，不将“最大字号”直接记为“2 倍”。窄屏优先用较小的真实设备复测；现有 Compose 测试覆盖 320dp 视口，但不能替代另一品牌真机结果。

## 9. 可选：在测试手机运行自动化

自动化验证首页状态和交互，使用测试状态，不代表真实模型链路通过。建议在手工激活**之前**执行；设备测试会安装测试应用，Gradle 结束时可能卸载被测应用，不能把日常使用设备的数据保留作为前提。

```sh
(
  cd android
  ./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest \
    -PGUOJING_DEBUG_API_BASE_URL=http://127.0.0.1:8000
  ANDROID_SERIAL="$GUOJING_TEST_SERIAL" ./gradlew connectedDebugAndroidTest \
    -PGUOJING_DEBUG_API_BASE_URL=http://127.0.0.1:8000
)
```

结果分别查看 `android/app/build/reports/tests/testDebugUnitTest/`、`android/app/build/reports/lint-results-debug.html` 和 `android/app/build/reports/androidTests/connected/`。测试后按第 4 节重新安装、检查服务和本机配置；若应用数据已被清除，使用新的邀请码。

## 10. 排查常见问题

| 现象 | 检查顺序 |
| --- | --- |
| Gradle 找不到 Java 或 SDK | 确认当前终端已设置第 2 节环境变量；在 SDK Manager 安装 Platform 37 / Build Tools 37.0.0，检查 Gradle JDK 21 配置 |
| APK 安装提示签名不一致 | 手机可能装了其他签名的同包名版本；使用匹配签名构建或换测试手机，不直接卸载正在使用的版本。卸载会丢失本机授权 |
| 首页说“就绪”，首次识别仍失败 | 就绪只代表本机准备完成；检查 `/ready`、邀请码有效性、模型密钥/图像能力及后端错误 |
| 手机浏览器也打不开 `/health` | 确认电脑服务正常、USB 连接为 `device`、端口映射存在；核对手机访问的是 `127.0.0.1:8000` |
| 浏览器能访问，应用连接失败 | 确认安装的是本次用 `GUOJING_DEBUG_API_BASE_URL` 构建的 APK；API 地址不能仅靠改 `.env.local` 更新 |
| 找不到“帮我” | 查看无障碍服务是否“已连接”、入口是否打开；到普通测试应用检查。服务被系统终止后重新进入系统设置确认连接 |
| 无障碍服务开关受系统限制 | 按手机系统提示核对应用来源与无障碍限制；不同厂商路径不同，不需要额外寻找普通悬浮窗权限 |
| 截图失败、提示保持页面稳定 | 回目标应用，关闭遮挡面板/键盘后再试；用不受保护的测试页面复测，不把受保护页面无法截图当作通用识别失败 |
| 邀请码已使用或过期 | 通过管理命令给新的测试安装重新邀请；首页“保存成功”不代表服务端接受邀请码 |
| 后端返回 503 或繁忙 | 查看电脑 `/ready`、Docker、迁移、磁盘和服务日志；按 [后端指南](startup-and-testing.md) 排查，不反复重装手机应用 |
| 语音没声音 | 检查媒体音量、系统 TTS 引擎及中文语音资源；仍需保证完整文字可手动滚动阅读 |

若应用闪退，可查看本次崩溃信息：

```sh
adb -s "$GUOJING_TEST_SERIAL" logcat -d -s AndroidRuntime:E
```

分享日志前检查并去掉个人资料、邀请码和凭据；不收集完整手机日志来代替复现步骤。

## 11. 保存验证记录并收尾

只在不含敏感内容的测试画面保存截图。在项目根目录执行，文件会放入已忽略的构建目录：

```sh
mkdir -p android/app/build/outputs/device-validation
adb -s "$GUOJING_TEST_SERIAL" exec-out screencap -p \
  > android/app/build/outputs/device-validation/home-normal.png
```

切换到大字号或任务页后可更改文件名再执行。这里是验证者主动保存的证据截图，不属于应用自动截图行为，记录时间时要区分。

每台手机填写一份记录；未执行项写“未测”，时序未触发写“未覆盖”，不要留空：

| 项目 | 记录 |
| --- | --- |
| 日期 / 验证者 |  |
| 手机品牌、型号、Android / 系统版本 |  |
| 代码版本（有未提交改动时注明）/ 构建时间 |  |
| 连接方式 / 测试目标应用 |  |
| 首次配置、格式错误、旋转草稿 | 通过 / 失败 / 未测 + 说明 |
| 普通字体、2 倍字体、横屏、窄屏 | 分别记录 |
| 目标确认前无新请求、取消不提交 | 结果 + 日志时段 |
| 首轮识别、多轮、语音与完整文字 | 结果 + 轮数 |
| 跨应用、旋转、服务断开恢复 | 分别记录 |
| 会话中换码限制、关闭取消/确认 | 分别记录 |
| 建会话前断网、任务中断网、进程恢复 | 分别记录 |
| 问题复现步骤、预期/实际、截图位置 |  |

完成后结束手机中的当前指引、恢复字体，移除本次 USB 映射；本次启动的后端可在终端 B 用 `Ctrl+C` 结束：

```sh
adb -s "$GUOJING_TEST_SERIAL" reverse --remove tcp:8000
```

截图、APK、日志、`.env.local` 不提交仓库。需要保留给团队的结论仅记录脱敏结果。

正式上线前还应使用签名 release 包与 HTTPS 服务，在至少两台真机、三人同时使用的场景复测。额度耗尽、设备停用等管理操作只放在独立测试环境：`revoke` 没有设备恢复命令，`resume` 只恢复全局接单，不能把它当作撤销停用。部署及额度验收参见 [试点部署学习记录](learning/61-cloud-pilot.md)。

## 附：不使用 USB 映射时的局域网方案

手机与电脑连接同一可信局域网，后端改为监听 `0.0.0.0:8000`；先停止原来的 API 进程，再启动，不能对同一数据库开两个服务：

```sh
uv run uvicorn guojing.main:app --host 0.0.0.0 --port 8000
```

将下面示例 IP 替换为电脑当前的局域网 IPv4 地址，重建并安装：

```sh
(
  cd android
  ./gradlew assembleDebug -PGUOJING_DEBUG_API_BASE_URL=http://192.168.1.100:8000
)
adb -s "$GUOJING_TEST_SERIAL" install -r android/app/build/outputs/apk/debug/app-debug.apk
```

先用手机浏览器访问对应 `/health`。连接失败时检查 Wi-Fi 隔离与电脑防火墙；本地调试服务不做路由器公网端口转发。此方案不使用 `adb reverse`，断网测试应关闭手机 Wi-Fi，并防止切到仍可访问服务的其他网络。release 包仍必须使用真实 HTTPS 地址及签名配置，见 [Android 启动与测试指南](android-startup-and-testing.md)。
