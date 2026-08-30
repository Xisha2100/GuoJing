package com.xisha.guojing.privacy

import org.junit.Assert.assertThrows
import org.junit.Test

class ScreenshotSanitizationReceiptTest {
    @Test
    fun receipt_rejects_redactions_and_no_sensitive_confirmation_together() {
        assertThrows(IllegalArgumentException::class.java) {
            ScreenshotSanitizationReceipt(
                redactionCount = 1,
                noSensitiveContentConfirmed = true,
                sanitizedSha256 = "a".repeat(64),
            )
        }
    }

    @Test
    fun receipt_rejects_zero_redactions_without_confirmation() {
        assertThrows(IllegalArgumentException::class.java) {
            ScreenshotSanitizationReceipt(
                redactionCount = 0,
                noSensitiveContentConfirmed = false,
                sanitizedSha256 = "a".repeat(64),
            )
        }
    }
}
