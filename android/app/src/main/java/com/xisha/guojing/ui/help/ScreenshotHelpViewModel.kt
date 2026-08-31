package com.xisha.guojing.ui.help

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.xisha.guojing.data.DisabledHelpRequestStatusReader
import com.xisha.guojing.data.DisabledHelpRequestSender
import com.xisha.guojing.data.HelpRequestIntent
import com.xisha.guojing.data.HelpRequestFormatException
import com.xisha.guojing.data.HelpRequestProcessingStatus
import com.xisha.guojing.data.HelpRequestReceipt
import com.xisha.guojing.data.HelpRequestSender
import com.xisha.guojing.data.HelpRequestStatusReader
import com.xisha.guojing.data.HelpRequestSubmission
import com.xisha.guojing.observation.DisabledScreenshotOcrProvider
import com.xisha.guojing.observation.ScreenshotOcrProvider
import com.xisha.guojing.privacy.InMemoryScreenshot
import com.xisha.guojing.privacy.NormalizedRedaction
import com.xisha.guojing.privacy.OcrPrivacySuggestionClassifier
import com.xisha.guojing.privacy.PlaintextReceiptCipher
import com.xisha.guojing.privacy.PrivacySuggestionDecision
import com.xisha.guojing.privacy.ReceiptCipher
import com.xisha.guojing.privacy.ScreenshotPrivacyProcessor
import com.xisha.guojing.privacy.ScreenshotSanitizationReceipt
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.Base64
import java.util.UUID

class ScreenshotHelpViewModel(
    private val processor: ScreenshotPrivacyProcessor,
    private val sender: HelpRequestSender = DisabledHelpRequestSender,
    private val ocrProvider: ScreenshotOcrProvider = DisabledScreenshotOcrProvider,
    private val suggestionClassifier: OcrPrivacySuggestionClassifier =
        OcrPrivacySuggestionClassifier(),
    private val statusReader: HelpRequestStatusReader = DisabledHelpRequestStatusReader,
    private val savedStateHandle: SavedStateHandle = SavedStateHandle(),
    private val receiptCipher: ReceiptCipher = PlaintextReceiptCipher,
) : ViewModel() {
    private val mutableUiState = MutableStateFlow<ScreenshotHelpUiState>(
        restoreSubmitted() ?: ScreenshotHelpUiState.AwaitingSelection(),
    )
    val uiState: StateFlow<ScreenshotHelpUiState> = mutableUiState.asStateFlow()

    private var processingJob: Job? = null

    fun importScreenshot(uriString: String) {
        if (uriString.isBlank()) return
        processingJob?.cancel()
        clearCurrentImage()
        clearPersistedReceipt()
        mutableUiState.value = ScreenshotHelpUiState.Importing
        processingJob = viewModelScope.launch {
            var imported: InMemoryScreenshot? = null
            try {
                val screenshot = processor.importFromPicker(uriString)
                imported = screenshot
                var ocrFailed = false
                val classification = try {
                    suggestionClassifier.classifyDetailed(ocrProvider.recognize(screenshot))
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Exception) {
                    ocrFailed = true
                    null
                }
                ensureActive()
                mutableUiState.value = ScreenshotHelpUiState.Editing(
                    screenshot = screenshot,
                    privacySuggestions = classification?.suggestions.orEmpty(),
                    privacySuggestionsTruncated = classification?.truncated == true,
                    error = when {
                        ocrFailed -> ScreenshotHelpError.OcrFailed
                        classification?.truncated == true ->
                            ScreenshotHelpError.OcrSuggestionsTruncated
                        else -> null
                    },
                )
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
        val removed = editing.redactions.last()
        mutableUiState.value = editing.copy(
            redactions = editing.redactions.dropLast(1),
            privacySuggestions = editing.privacySuggestions.map { suggestion ->
                if (suggestion.decision == PrivacySuggestionDecision.Accepted &&
                    suggestion.bounds == removed
                ) {
                    suggestion.copy(decision = PrivacySuggestionDecision.Pending)
                } else {
                    suggestion
                }
            },
            error = null,
        )
    }

    fun acceptPrivacySuggestion(suggestionId: String) {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        val suggestion = editing.privacySuggestions.firstOrNull { it.id == suggestionId }
            ?: return
        if (suggestion.decision != PrivacySuggestionDecision.Pending) return
        if (editing.redactions.size >= MAX_REDACTIONS) return
        mutableUiState.value = editing.copy(
            redactions = editing.redactions + suggestion.bounds,
            privacySuggestions = editing.privacySuggestions.map {
                if (it.id == suggestionId) {
                    it.copy(decision = PrivacySuggestionDecision.Accepted)
                } else {
                    it
                }
            },
            noSensitiveContentConfirmed = false,
            error = null,
        )
    }

    fun rejectPrivacySuggestion(suggestionId: String) {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        if (editing.privacySuggestions.none {
                it.id == suggestionId && it.decision == PrivacySuggestionDecision.Pending
            }
        ) return
        mutableUiState.value = editing.copy(
            privacySuggestions = editing.privacySuggestions.map {
                if (it.id == suggestionId) {
                    it.copy(decision = PrivacySuggestionDecision.Rejected)
                } else {
                    it
                }
            },
            error = null,
        )
    }

    fun setNoSensitiveContentConfirmed(confirmed: Boolean) {
        val editing = mutableUiState.value as? ScreenshotHelpUiState.Editing ?: return
        if (confirmed && (editing.redactions.isNotEmpty() || editing.privacySuggestions.any {
                it.decision == PrivacySuggestionDecision.Pending
            })) return
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
                    clientRequestId = UUID.randomUUID().toString(),
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

    fun selectIntent(intent: HelpRequestIntent) {
        val ready = mutableUiState.value as? ScreenshotHelpUiState.Ready ?: return
        mutableUiState.value = ready.copy(intent = intent, error = null)
    }

    fun setSendConsent(confirmed: Boolean) {
        val ready = mutableUiState.value as? ScreenshotHelpUiState.Ready ?: return
        mutableUiState.value = ready.copy(sendConsent = confirmed, error = null)
    }

    fun send() {
        val ready = mutableUiState.value as? ScreenshotHelpUiState.Ready ?: return
        if (!ready.canSend) return
        processingJob?.cancel()
        mutableUiState.value = ScreenshotHelpUiState.Sending(
            screenshot = ready.screenshot,
            question = ready.question,
            receipt = ready.receipt,
            clientRequestId = ready.clientRequestId,
            intent = ready.intent,
        )
        processingJob = viewModelScope.launch {
            try {
                val serverReceipt = sender.send(
                    HelpRequestSubmission(
                        screenshot = ready.screenshot,
                        question = ready.question,
                        receipt = ready.receipt,
                        intent = ready.intent,
                        clientRequestId = ready.clientRequestId,
                    ),
                )
                ensureActive()
                ready.screenshot.erase()
                val submitted = ScreenshotHelpUiState.Submitted(
                    question = ready.question,
                    receipt = ready.receipt,
                    intent = ready.intent,
                    serverReceipt = serverReceipt,
                    processingStatus = serverReceipt.processingStatus,
                )
                mutableUiState.value = submitted
                runCatching {
                    persistReceipt(
                        question = ready.question,
                        sanitizationReceipt = ready.receipt,
                        intent = ready.intent,
                        serverReceipt = serverReceipt,
                    )
                }
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                mutableUiState.value = ready.copy(error = ScreenshotHelpError.SendFailed)
            }
        }
    }

    fun refreshStatus() {
        val submitted = mutableUiState.value as? ScreenshotHelpUiState.Submitted ?: return
        if (submitted.isRefreshingStatus) return
        processingJob?.cancel()
        mutableUiState.value = submitted.copy(
            isRefreshingStatus = true,
            statusError = null,
        )
        processingJob = viewModelScope.launch {
            try {
                val result = statusReader.fetch(
                    submitted.serverReceipt.requestId,
                    submitted.serverReceipt.accessToken,
                )
                if (result.clientRequestId != submitted.serverReceipt.clientRequestId ||
                    result.intent != submitted.intent ||
                    result.processingRoute != submitted.serverReceipt.processingRoute
                ) {
                    throw HelpRequestFormatException(
                        "Help request result does not match the submitted receipt",
                    )
                }
                ensureActive()
                val current = mutableUiState.value as? ScreenshotHelpUiState.Submitted
                    ?: return@launch
                mutableUiState.value = current.copy(
                    processingStatus = result.processingStatus,
                    workflowStage = result.workflowStage,
                    tutorialMatch = result.tutorialMatch,
                    tutorialPlan = result.tutorialPlan,
                    guidance = result.guidance,
                    humanReviewReason = result.humanReviewReason,
                    isRefreshingStatus = false,
                    statusError = null,
                )
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                val current = mutableUiState.value as? ScreenshotHelpUiState.Submitted
                    ?: return@launch
                mutableUiState.value = current.copy(
                    isRefreshingStatus = false,
                    statusError = ScreenshotHelpError.StatusFetchFailed,
                )
            }
        }
    }

    fun discard() {
        processingJob?.cancel()
        processingJob = null
        clearCurrentImage()
        clearPersistedReceipt()
        mutableUiState.value = ScreenshotHelpUiState.AwaitingSelection()
    }

    private fun clearCurrentImage() {
        when (val current = mutableUiState.value) {
            is ScreenshotHelpUiState.Editing -> current.screenshot.erase()
            is ScreenshotHelpUiState.Sanitizing -> current.screenshot.erase()
            is ScreenshotHelpUiState.Ready -> current.screenshot.erase()
            is ScreenshotHelpUiState.Sending -> current.screenshot.erase()
            is ScreenshotHelpUiState.AwaitingSelection,
            ScreenshotHelpUiState.Importing,
            is ScreenshotHelpUiState.Submitted,
            -> Unit
        }
    }

    private fun persistReceipt(
        question: String,
        sanitizationReceipt: ScreenshotSanitizationReceipt,
        intent: HelpRequestIntent,
        serverReceipt: HelpRequestReceipt,
    ) {
        val fields = listOf(
            question,
            sanitizationReceipt.redactionCount.toString(),
            sanitizationReceipt.noSensitiveContentConfirmed.toString(),
            sanitizationReceipt.sanitizedSha256,
            intent.wireValue,
            serverReceipt.requestId,
            serverReceipt.clientRequestId,
            serverReceipt.processingRoute,
            serverReceipt.processingStatus.wireValue,
            serverReceipt.statusEndpoint,
            serverReceipt.accessToken,
        ).map(::encodeField)
        savedStateHandle[KEY_ENCRYPTED_RECEIPT] = receiptCipher.encrypt(fields.joinToString("|"))
    }

    private fun restoreSubmitted(): ScreenshotHelpUiState.Submitted? {
        return try {
            val encoded = savedStateHandle.get<String>(KEY_ENCRYPTED_RECEIPT) ?: return null
            val fields = receiptCipher.decrypt(encoded)?.split("|")?.map(::decodeField)
                ?: return null
            if (fields.size != RECEIPT_FIELD_COUNT) return null
            val question = fields[0]
            val intent = HelpRequestIntent.fromWire(fields[4])
            val status = HelpRequestProcessingStatus.fromWire(fields[8])
            val receipt = ScreenshotSanitizationReceipt(
                redactionCount = fields[1].toInt(),
                noSensitiveContentConfirmed = fields[2].toBooleanStrict(),
                sanitizedSha256 = fields[3],
            )
            ScreenshotHelpUiState.Submitted(
                question = question,
                receipt = receipt,
                intent = intent,
                serverReceipt = HelpRequestReceipt(
                    requestId = fields[5],
                    clientRequestId = fields[6],
                    intent = intent,
                    processingRoute = fields[7],
                    processingStatus = status,
                    statusEndpoint = fields[9],
                    accessToken = fields[10],
                ),
                processingStatus = status,
            )
        } catch (_: Exception) {
            clearPersistedReceipt()
            null
        }
    }

    private fun clearPersistedReceipt() {
        savedStateHandle.remove<Any>(KEY_ENCRYPTED_RECEIPT)
    }

    private fun encodeField(value: String): String =
        Base64.getUrlEncoder().withoutPadding().encodeToString(value.toByteArray(Charsets.UTF_8))

    private fun decodeField(value: String): String =
        String(Base64.getUrlDecoder().decode(value), Charsets.UTF_8)

    override fun onCleared() {
        processingJob?.cancel()
        clearCurrentImage()
        super.onCleared()
    }

    companion object {
        fun factory(
            processor: ScreenshotPrivacyProcessor,
            sender: HelpRequestSender = DisabledHelpRequestSender,
            ocrProvider: ScreenshotOcrProvider = DisabledScreenshotOcrProvider,
            statusReader: HelpRequestStatusReader = DisabledHelpRequestStatusReader,
            receiptCipher: ReceiptCipher = PlaintextReceiptCipher,
        ): ViewModelProvider.Factory =
            viewModelFactory {
                initializer {
                    ScreenshotHelpViewModel(
                        processor = processor,
                        sender = sender,
                        ocrProvider = ocrProvider,
                        statusReader = statusReader,
                        savedStateHandle = createSavedStateHandle(),
                        receiptCipher = receiptCipher,
                    )
                }
            }

        private const val MAX_QUESTION_LENGTH = 300
        private const val MAX_REDACTIONS = 20
        private const val KEY_ENCRYPTED_RECEIPT = "help.encrypted_receipt"
        private const val RECEIPT_FIELD_COUNT = 11
    }
}
