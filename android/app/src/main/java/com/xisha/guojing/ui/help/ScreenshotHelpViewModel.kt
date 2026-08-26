package com.xisha.guojing.ui.help

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.ScreenshotPrivacyProcessor
import com.xisha.guojing.privacy.ScreenshotSanitizationReceipt
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ScreenshotHelpViewModel(
    private val processor: ScreenshotPrivacyProcessor,
) : ViewModel() {
    private val mutableUiState = MutableStateFlow<ScreenshotHelpUiState>(
        ScreenshotHelpUiState.AwaitingSelection(),
    )
    val uiState: StateFlow<ScreenshotHelpUiState> = mutableUiState.asStateFlow()

    private var processingJob: Job? = null

    fun importScreenshot(uriString: String) {
        if (uriString.isBlank()) return
        processingJob?.cancel()
        clearCurrentImage()
        mutableUiState.value = ScreenshotHelpUiState.Importing
        processingJob = viewModelScope.launch {
            var imported: InMemoryScreenshot? = null
            try {
                imported = processor.importFromPicker(uriString)
                ensureActive()
                mutableUiState.value = ScreenshotHelpUiState.Editing(imported)
            } catch (error: CancellationException) {
                imported?.erase()
                throw error
            } catch (_: Exception) {
                imported?.erase()
                mutableUiState.value = ScreenshotHelpUiState.AwaitingSelection(
                    ScreenshotHelpError.ImportFailed,
                )
            }
        }
    }

    fun updateQuestion(value: String) {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        mutableUiState.value = editing.copy(
            question = value.take(MAX_QUESTION_LENGTH),
            error = null,
        )
    }

    fun addRedaction(redaction: NormalizedRedaction) {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        if (editing.redactions.size >= MAX_REDACTIONS) return
        mutableUiState.value = editing.copy(
            redactions = editing.redactions + redaction,
            noSensitiveContentConfirmed = false,
            error = null,
        )
    }

    fun undoLastRedaction() {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        if (editing.redactions.isEmpty()) return
        mutableUiState.value = editing.copy(
            redactions = editing.redactions.dropLast(1),
            error = null,
        )
    }

    fun setNoSensitiveContentConfirmed(confirmed: Boolean) {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        mutableUiState.value = editing.copy(
            noSensitiveContentConfirmed = confirmed,
            error = null,
        )
    }

    fun sanitize() {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        if (!editing.canSanitize) return
        processingJob?.cancel()
        mutableUiState.value = ScreenshotHelpUiState.Sanitizing(
            screenshot = editing.screenshot,
            question = editing.question.trim(),
            redactions = editing.redactions,
            noSensitiveContentConfirmed = editing.noSensitiveContentConfirmed,
        )
        processingJob = viewModelScope.launch {
            var sanitized: InMemoryScreenshot? = null
            try {
                sanitized = processor.sanitize(editing.screenshot, editing.redactions)
                ensureActive()
                editing.screenshot.erase()
                mutableUiState.value = ScreenshotHelpUiState.Ready(
                    screenshot = sanitized,
                    question = editing.question.trim(),
                    receipt = ScreenshotSanitizationReceipt(
                        redactionCount = editing.redactions.size,
                        noSensitiveContentConfirmed = editing.noSensitiveContentConfirmed,
                        sanitizedSha256 = sanitized.sha256,
                    ),
                )
            } catch (error: CancellationException) {
                sanitized?.erase()
                throw error
            } catch (_: Exception) {
                sanitized?.erase()
                mutableUiState.value = editing.copy(
                    error = ScreenshotHelpError.SanitizationFailed,
                )
            }
        }
    }

    fun discard() {
        processingJob?.cancel()
        processingJob = null
        clearCurrentImage()
        mutableUiState.value = ScreenshotHelpUiState.AwaitingSelection()
    }

    private fun clearCurrentImage() {
        when (val current = mutableUiState.value) {
            is ScreenshotHelpUiState.Editing -> current.screenshot.erase()
            is ScreenshotHelpUiState.Sanitizing -> current.screenshot.erase()
            is ScreenshotHelpUiState.Ready -> current.screenshot.erase()
            is ScreenshotHelpUiState.AwaitingSelection,
            ScreenshotHelpUiState.Importing,
            -> Unit
        }
    }

    override fun onCleared() {
        processingJob?.cancel()
        clearCurrentImage()
        super.onCleared()
    }

    companion object {
        fun factory(processor: ScreenshotPrivacyProcessor): ViewModelProvider.Factory =
            viewModelFactory {
                initializer {
                    ScreenshotHelpViewModel(processor)
                }
            }

        private const val MAX_QUESTION_LENGTH = 300
        private const val MAX_REDACTIONS = 20
    }
}
