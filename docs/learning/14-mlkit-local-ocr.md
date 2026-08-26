# 模块 14：ML Kit 本地 OCR 适配器

## 1. 本模块做了什么

模块 13 只有 OCR 证据合同，本模块接入第一个真实 provider：Android 端打包式 ML Kit Text Recognition v2。

```text
InMemoryScreenshot
  → BitmapFactory 解码（仅内存）
  → ML Kit 中文 recognizer + Latin recognizer
  → Text.Line 原文和像素矩形
  → OcrTextBlock（临时）
  → OcrObservationBuilder
  → anchor_id + confidence + normalized_bounds
```

当前 provider 只负责识别，不决定教程是否匹配，也不执行任何第三方 APP 操作。

## 2. 为什么选择打包模型

ML Kit 提供两种安装方式：模型随应用打包，或者通过 Google Play Services 动态下载。当前选择打包模型：

- 中文：`com.google.mlkit:text-recognition-chinese:16.0.1`；
- Latin：`com.google.mlkit:text-recognition:16.0.1`。

打包模型会增加 APK 体积，但首次识别不依赖网络，适合老人帮助场景和确定性的 Pixel 7 测试。动态模型包体更小，却需要处理“模型还没下载完成”的等待、失败和离线提示。官方文档还说明，模型下载完成前提交的识别请求不会返回结果：
<https://developers.google.com/ml-kit/vision/text-recognition/v2/android?hl=zh-cn>

这两个库的版本通过 `android/gradle/libs.versions.toml` 统一管理，和 Java 项目用 Maven BOM 或版本目录集中管理依赖是同一类实践。

## 3. Kotlin adapter 如何隔离 SDK

`MlKitScreenshotOcrProvider` 实现 `ScreenshotOcrProvider`：

```kotlin
interface ScreenshotOcrProvider : AutoCloseable {
    suspend fun recognize(source: InMemoryScreenshot): List<OcrTextBlock>
}
```

ViewModel 或未来的 use case 只依赖这个接口，不需要知道 `TextRecognition.getClient()`、`Text.Line` 或 Google Task。以后替换成 Tesseract、后端 worker 或视觉模型时，只新增 adapter，不改 `OcrObservationBuilder`。

这对应 Java 后端常见的 `OcrPort` + infrastructure adapter：application 层依赖接口，框架 SDK 只在 infrastructure 边界出现。

## 4. Task 到 suspend 的桥接

ML Kit 的 `process()` 返回 Google Play Services `Task<T>`，项目的业务代码使用 Kotlin coroutine。因此 provider 用 `suspendCancellableCoroutine` 将三种结果映射为协程状态：

```text
addOnSuccessListener → resume
addOnFailureListener → resumeWithException
addOnCanceledListener → cancel coroutine
```

识别失败会沿协程异常路径返回给调用方，不会伪造空的“识别成功”。这和 Java 中把 `CompletableFuture` 适配为同步业务接口类似，但 Kotlin 可以直接在结构化并发里传播取消。

## 5. 为什么使用 Text.Line 而不是整张 Text

ML Kit 返回文本块、行、单词和字符层级。我们选择行级结果：

- 一个行矩形足够和教程的 `ocr_text` 锚点匹配；
- 比字符级结果小，减少临时对象和重复边界；
- 中文和 Latin recognizer 可能识别到相同文字，provider 用规范化文字和归一化边界去重。

provider 不返回整段 `result.text`，也不把原文写入 `ScreenObservation`。builder 消费 `OcrTextBlock` 后，页面匹配只看到锚点证据。

## 6. 像素坐标如何变成归一化坐标

ML Kit 的矩形是像素坐标，浮层和教程模型使用 0 到 1 的归一化坐标：

```text
left   = clamp(rect.left   / bitmap.width)
top    = clamp(rect.top    / bitmap.height)
right  = clamp(rect.right  / bitmap.width)
bottom = clamp(rect.bottom / bitmap.height)
```

在转换前会裁剪到图片范围，并拒绝宽度或高度为零的矩形。这样 OCR 证据可以和 Accessibility 的 `NormalizedScreenBounds` 使用同一套 matcher 和浮层布局，不依赖某一台手机的分辨率。

## 7. 图片和原文的生命周期

`InMemoryScreenshot` 由 privacy 模块拥有。provider 只借用其字节：

1. 解码出临时 `Bitmap`；
2. 在 `try/finally` 中运行两个 recognizer；
3. 无论成功或异常都 `recycle()` Bitmap；
4. 调用方在不再需要 OCR 结果时清理 `OcrTextBlock` 和原始截图。

provider 自身不保存图片、不写文件、不上传网络，也不负责擦除调用方的 `InMemoryScreenshot`。所有权分离避免一个 adapter 擅自清理仍被 UI 使用的对象。

## 8. 测试

JVM 测试继续验证模块 13 的隐私和匹配规则。新增 Pixel 7 instrumentation test：

- 在内存 Bitmap 上绘制 `HELP 123`；
- 压缩为临时字节，不写图库；
- 调用打包 ML Kit provider；
- 验证识别到文字以及非空归一化边界；
- finally 中关闭 recognizer、擦除截图字节。

真实 OCR 测试必须放在设备端，因为 JVM 没有 Android Bitmap、ML Kit native pipeline 和模型运行时。测试样本是程序生成的，不包含真实用户信息。

## 9. 当前限制与下一模块

- provider 已实现，但尚未在截图求助 UI 中自动运行；这样可以先观察模型质量，再决定如何显示候选隐私区域。
- 现在只返回文字行，尚未分类姓名、电话、余额、订单号或二维码。
- ML Kit 的置信度不是安全证明；低置信度只能降低匹配分，不能自动操作。
- 图片旋转、复杂透视、极小字体和中文字体覆盖需要用受控样本继续基准测试。

下一模块将把本地 OCR 结果用于“可能的隐私区域建议”：建议可以帮助用户，但必须由用户逐项确认，不能自动遮挡后直接发送。
