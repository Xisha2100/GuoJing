package com.xisha.guojing.ui.help

import com.xisha.guojing.data.HelpRequestIntent
import com.xisha.guojing.data.HelpRequestReceipt
import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.OcrPrivacySuggestion
import com.xisha.guojing.privacy.PrivacySuggestionDecision
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
        val privacySuggestions: List<OcrPrivacySuggestion> = emptyList(),
        val noSensitiveContentConfirmed: Boolean = false,
        val error: ScreenshotHelpError? = null,
    ) : ScreenshotHelpUiState {
        val canSanitize: Boolean
            get() = question.isNotBlank() &&
                privacySuggestions.none {
                    it.decision == PrivacySuggestionDecision.Pending
                } &&
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
        val intent: HelpRequestIntent = HelpRequestIntent.GENERAL_GUIDANCE,
        val sendConsent: Boolean = false,
        val error: ScreenshotHelpError? = null,
    ) : ScreenshotHelpUiState {
        val canSend: Boolean
            get() = sendConsent && question.isNotBlank()
    }

    data class Sending(
        val screenshot: InMemoryScreenshot,
        val question: String,
        val receipt: ScreenshotSanitizationReceipt,
        val intent: HelpRequestIntent,
    ) : ScreenshotHelpUiState

    data class Submitted(
        val question: String,
        val receipt: ScreenshotSanitizationReceipt,
        val intent: HelpRequestIntent,
        val serverReceipt: HelpRequestReceipt,
    ) : ScreenshotHelpUiState
}

enum class ScreenshotHelpError {
    ImportFailed,
    OcrFailed,
    SanitizationFailed,
    SendFailed,
}
