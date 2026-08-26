package com.xisha.guojing.ui.help

import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.ScreenshotSanitizationReceipt

sealed interface ScreenshotHelpUiState {
    data class AwaitingSelection(
        val error: ScreenshotHelpError? = null,
    ) : ScreenshotHelpUiState

    data object Importing : ScreenshotHelpUiState

    data class Editing(
        val screenshot: InMemoryScreenshot,
        val question: String = "",
        val redactions: List<NormalizedRedaction> = emptyList(),
        val noSensitiveContentConfirmed: Boolean = false,
        val error: ScreenshotHelpError? = null,
    ) : ScreenshotHelpUiState {
        val canSanitize: Boolean
            get() = question.isNotBlank() &&
                (redactions.isNotEmpty() || noSensitiveContentConfirmed)
    }

    data class Sanitizing(
        val screenshot: InMemoryScreenshot,
        val question: String,
        val redactions: List<NormalizedRedaction>,
        val noSensitiveContentConfirmed: Boolean,
    ) : ScreenshotHelpUiState

    data class Ready(
        val screenshot: InMemoryScreenshot,
        val question: String,
        val receipt: ScreenshotSanitizationReceipt,
    ) : ScreenshotHelpUiState
}

enum class ScreenshotHelpError {
    ImportFailed,
    SanitizationFailed,
}
