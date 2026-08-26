package com.xisha.guojing.privacy

interface ScreenshotPrivacyProcessor {
    suspend fun importFromPicker(uriString: String): InMemoryScreenshot

    suspend fun sanitize(
        source: InMemoryScreenshot,
        redactions: List<NormalizedRedaction>,
    ): InMemoryScreenshot
}

object DisabledScreenshotPrivacyProcessor : ScreenshotPrivacyProcessor {
    override suspend fun importFromPicker(uriString: String): InMemoryScreenshot =
        error("Screenshot privacy processing is not configured")

    override suspend fun sanitize(
        source: InMemoryScreenshot,
        redactions: List<NormalizedRedaction>,
    ): InMemoryScreenshot = error("Screenshot privacy processing is not configured")
}
