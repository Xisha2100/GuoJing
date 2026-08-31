package com.xisha.guojing.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.execution.TutorialExecutionEngine
import com.xisha.guojing.execution.TutorialExecutionStage
import com.xisha.guojing.guidance.DisabledGuidanceOverlayPort
import com.xisha.guojing.guidance.GuidanceOverlayCommand
import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.model.TutorialNode
import com.xisha.guojing.model.RiskLevel
import com.xisha.guojing.observation.DisabledScreenObservationPort
import com.xisha.guojing.observation.ObservationRequest
import com.xisha.guojing.observation.ObservationSharingPolicy
import com.xisha.guojing.observation.ObservationState
import com.xisha.guojing.observation.ScreenMatchStatus
import com.xisha.guojing.observation.ScreenObservationPort
import com.xisha.guojing.observation.VersionCompatibility
import com.xisha.guojing.observation.assessVersionCompatibility
import com.xisha.guojing.observation.matchScreen
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TutorialDetailViewModel(
    private val graphId: String,
    private val repository: TutorialDetailRepository,
    private val observationPort: ScreenObservationPort = DisabledScreenObservationPort,
    private val overlayPort: GuidanceOverlayPort = DisabledGuidanceOverlayPort,
) : ViewModel() {
    private val mutableUiState = MutableStateFlow<TutorialDetailUiState>(
        TutorialDetailUiState.Loading,
    )
    val uiState: StateFlow<TutorialDetailUiState> = mutableUiState.asStateFlow()

    private var loadJob: Job? = null
    private var executionEngine: TutorialExecutionEngine? = null
    private var consecutiveTargetMatches = 0

    init {
        observePageEvidence()
        load()
    }

    fun retry() {
        load()
    }

    fun startTutorial() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        if (!content.tutorial.safetyPresentation().canStart) return
        val engine = TutorialExecutionEngine(content.tutorial.graph)
        executionEngine = engine
        val stage = engine.start()
        mutableUiState.value = content.copy(
            mode = TutorialDetailMode.Execution(stage),
        )
        observeStage(content.tutorial.graph, stage)
    }

    fun confirmStepCompleted(requirePageVerification: Boolean = false) {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        val execution = content.mode as? TutorialDetailMode.Execution ?: return
        val step = execution.stage as? TutorialExecutionStage.Step ?: return
        if (execution.transitionVerification != TransitionVerificationStatus.Ready) return
        val engine = executionEngine ?: return
        // A version-drift match is only a provisional low-risk trial.  Even
        // when the UI callback uses its normal default, require the expected
        // target page before promoting the step and moving on.
        val mustVerifyTarget = requirePageVerification ||
            execution.pageObservation is PageObservationStatus.VersionChanged
        if (!mustVerifyTarget) {
            advanceStep(content, step, engine)
            return
        }

        overlayPort.hide()
        consecutiveTargetMatches = 0
        val targetNode = content.tutorial.graph.node(step.transition.targetNodeId)
        if (targetNode == null) {
            updateTargetVerification(
                content = content,
                execution = execution,
                pageObservation = PageObservationStatus.Mismatch,
                verification = TransitionVerificationStatus.TargetMismatch,
            )
            return
        }
        mutableUiState.value = content.copy(
            mode = execution.copy(
                pageObservation = PageObservationStatus.WaitingForTargetApp,
                transitionVerification = TransitionVerificationStatus.CheckingTarget(
                    matchedObservations = 0,
                    requiredObservations = REQUIRED_TARGET_MATCHES,
                ),
            ),
        )
        observeNode(content.tutorial.graph, targetNode)
    }

    fun exitExecution() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        executionEngine = null
        consecutiveTargetMatches = 0
        observationPort.stop()
        overlayPort.hide()
        mutableUiState.value = content.copy(mode = TutorialDetailMode.Overview)
    }

    private fun load() {
        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            executionEngine = null
            consecutiveTargetMatches = 0
            observationPort.stop()
            overlayPort.hide()
            mutableUiState.value = TutorialDetailUiState.Loading
            mutableUiState.value = try {
                TutorialDetailUiState.Content(repository.getPublishedTutorial(graphId))
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                TutorialDetailUiState.Error
            }
        }
    }

    private fun observePageEvidence() {
        viewModelScope.launch {
            observationPort.state.collect { observationState ->
                val content = mutableUiState.value as? TutorialDetailUiState.Content
                    ?: return@collect
                val execution = content.mode as? TutorialDetailMode.Execution
                    ?: return@collect
                handleObservation(content, execution, observationState)
            }
        }
    }

    private fun handleObservation(
        content: TutorialDetailUiState.Content,
        execution: TutorialDetailMode.Execution,
        observationState: ObservationState,
    ) {
        val graph = content.tutorial.graph
        val step = execution.stage as? TutorialExecutionStage.Step
        val request = observationState.requestOrNull()
        val isTargetVerification = step != null &&
            execution.transitionVerification !is TransitionVerificationStatus.Ready &&
            request?.nodeId == step.transition.targetNodeId
        if (isTargetVerification) {
            handleTargetObservation(content, execution, step, observationState)
            return
        }

        val status = observationState.toPageStatus(
            graph,
            execution.stage.node,
            step?.transition,
        )
        if ((status is PageObservationStatus.Matched ||
                status is PageObservationStatus.VersionChanged) &&
            step != null &&
            observationState is ObservationState.Available
        ) {
            showGuidance(step, observationState.observation, observationState.sequence)
        } else {
            overlayPort.hide()
        }
        mutableUiState.value = content.copy(
            mode = execution.copy(pageObservation = status),
        )
    }

    private fun handleTargetObservation(
        content: TutorialDetailUiState.Content,
        execution: TutorialDetailMode.Execution,
        step: TutorialExecutionStage.Step,
        observationState: ObservationState,
    ) {
        overlayPort.hide()
        val targetNode = content.tutorial.graph.node(step.transition.targetNodeId)
            ?: return
        when (observationState) {
            ObservationState.Idle,
            is ObservationState.Waiting,
            -> updateTargetVerification(
                content,
                execution,
                PageObservationStatus.WaitingForTargetApp,
                TransitionVerificationStatus.CheckingTarget(
                    consecutiveTargetMatches,
                    REQUIRED_TARGET_MATCHES,
                ),
            )
            is ObservationState.CapturePaused -> updateTargetVerification(
                content,
                execution,
                PageObservationStatus.CapturePaused,
                TransitionVerificationStatus.CapturePaused,
            )
            is ObservationState.Available -> {
                val result = matchScreen(content.tutorial.graph, targetNode, observationState.observation)
                when (result.status) {
                    ScreenMatchStatus.Matched -> {
                        val version = assessVersionCompatibility(
                            targetNode,
                            observationState.observation.app,
                        )
                        when (version) {
                            VersionCompatibility.SameVerifiedVersion -> onTargetMatched(
                                content = content,
                                execution = execution,
                                step = step,
                                score = result.score,
                                localOnly = observationState.observation.sharingPolicy ==
                                    ObservationSharingPolicy.LocalOnly,
                                pageObservation = PageObservationStatus.Matched(
                                    result.score,
                                    observationState.observation.sharingPolicy ==
                                        ObservationSharingPolicy.LocalOnly,
                                ),
                            )
                            VersionCompatibility.VersionChanged -> if (step.transition.isLowRiskTrial()) {
                                onTargetMatched(
                                    content = content,
                                    execution = execution,
                                    step = step,
                                    score = result.score,
                                    localOnly = observationState.observation.sharingPolicy ==
                                        ObservationSharingPolicy.LocalOnly,
                                    pageObservation = PageObservationStatus.VersionChanged(
                                        result.score,
                                        observationState.observation.sharingPolicy ==
                                            ObservationSharingPolicy.LocalOnly,
                                    ),
                                )
                            } else {
                                consecutiveTargetMatches = 0
                                updateTargetVerification(
                                    content,
                                    execution,
                                    PageObservationStatus.VersionStale,
                                    TransitionVerificationStatus.TargetMismatch,
                                )
                            }
                            VersionCompatibility.StoredStale -> {
                                consecutiveTargetMatches = 0
                                updateTargetVerification(
                                    content,
                                    execution,
                                    PageObservationStatus.VersionStale,
                                    TransitionVerificationStatus.TargetMismatch,
                                )
                            }
                            VersionCompatibility.UnknownCurrentVersion -> {
                                consecutiveTargetMatches = 0
                                updateTargetVerification(
                                    content,
                                    execution,
                                    PageObservationStatus.Uncertain(result.score),
                                    TransitionVerificationStatus.TargetUncertain,
                                )
                            }
                        }
                    }
                    ScreenMatchStatus.Uncertain -> {
                        consecutiveTargetMatches = 0
                        updateTargetVerification(
                            content,
                            execution,
                            PageObservationStatus.Uncertain(result.score),
                            TransitionVerificationStatus.TargetUncertain,
                        )
                    }
                    ScreenMatchStatus.Mismatch -> {
                        consecutiveTargetMatches = 0
                        updateTargetVerification(
                            content,
                            execution,
                            PageObservationStatus.Mismatch,
                            TransitionVerificationStatus.TargetMismatch,
                        )
                    }
                }
            }
        }
    }

    private fun onTargetMatched(
        content: TutorialDetailUiState.Content,
        execution: TutorialDetailMode.Execution,
        step: TutorialExecutionStage.Step,
        score: Double,
        localOnly: Boolean,
        pageObservation: PageObservationStatus = PageObservationStatus.Matched(score, localOnly),
    ) {
        consecutiveTargetMatches += 1
        if (consecutiveTargetMatches < REQUIRED_TARGET_MATCHES) {
            updateTargetVerification(
                content,
                execution,
                pageObservation,
                TransitionVerificationStatus.CheckingTarget(
                    consecutiveTargetMatches,
                    REQUIRED_TARGET_MATCHES,
                ),
            )
            return
        }
        val engine = executionEngine ?: return
        advanceStep(content, step, engine)
    }

    private fun updateTargetVerification(
        content: TutorialDetailUiState.Content,
        execution: TutorialDetailMode.Execution,
        pageObservation: PageObservationStatus,
        verification: TransitionVerificationStatus,
    ) {
        mutableUiState.value = content.copy(
            mode = execution.copy(
                pageObservation = pageObservation,
                transitionVerification = verification,
            ),
        )
    }

    private fun showGuidance(
        step: TutorialExecutionStage.Step,
        observation: com.xisha.guojing.observation.ScreenObservation,
        observationSequence: Long,
    ) {
        val targetEvidence = step.transition.targetAnchorId?.let { targetAnchorId ->
            observation.anchorEvidence.firstOrNull { evidence ->
                evidence.anchorId == targetAnchorId && evidence.confidence >= 0.80
            }
        }
        overlayPort.show(
            GuidanceOverlayCommand(
                targetPackageName = observation.app.packageName,
                stepNumber = step.stepNumber,
                instruction = step.transition.instruction,
                targetBounds = targetEvidence?.normalizedBounds,
                graphId = observation.request.graphId,
                nodeId = observation.request.nodeId,
                observationSequence = observationSequence,
            ),
        )
    }

    private fun advanceStep(
        content: TutorialDetailUiState.Content,
        step: TutorialExecutionStage.Step,
        engine: TutorialExecutionEngine,
    ) {
        consecutiveTargetMatches = 0
        overlayPort.hide()
        val nextStage = engine.advance(step)
        mutableUiState.value = content.copy(mode = TutorialDetailMode.Execution(nextStage))
        observeStage(content.tutorial.graph, nextStage)
    }

    private fun observeStage(graph: TutorialGraph, stage: TutorialExecutionStage) {
        val node = stage.node
        if (stage is TutorialExecutionStage.Step) {
            observeNode(graph, node)
        } else {
            observationPort.stop()
            overlayPort.hide()
        }
    }

    private fun observeNode(graph: TutorialGraph, node: TutorialNode) {
        observationPort.observe(
            ObservationRequest(
                graphId = graph.graphId,
                nodeId = node.nodeId,
                targetPackageName = graph.recordedApp.packageName,
                anchors = node.anchors,
                privacyMode = node.privacyMode,
            ),
        )
    }

    private fun ObservationState.toPageStatus(
        graph: TutorialGraph,
        node: TutorialNode,
        transition: com.xisha.guojing.model.TutorialTransition? = null,
    ): PageObservationStatus = when (this) {
        ObservationState.Idle -> PageObservationStatus.NotStarted
        is ObservationState.CapturePaused -> PageObservationStatus.CapturePaused
        is ObservationState.Waiting -> PageObservationStatus.WaitingForTargetApp
        is ObservationState.Available -> {
            if (observation.request.nodeId != node.nodeId) {
                PageObservationStatus.WaitingForTargetApp
            } else {
                val result = matchScreen(graph, node, observation)
                when (result.status) {
                    ScreenMatchStatus.Matched -> when (
                        assessVersionCompatibility(node, observation.app)
                    ) {
                        VersionCompatibility.SameVerifiedVersion -> PageObservationStatus.Matched(
                            score = result.score,
                            localOnly = observation.sharingPolicy ==
                                ObservationSharingPolicy.LocalOnly,
                        )
                        VersionCompatibility.VersionChanged -> if (transition?.isLowRiskTrial() == true) {
                            PageObservationStatus.VersionChanged(
                                score = result.score,
                                localOnly = observation.sharingPolicy ==
                                    ObservationSharingPolicy.LocalOnly,
                            )
                        } else {
                            PageObservationStatus.VersionStale
                        }
                        VersionCompatibility.StoredStale -> PageObservationStatus.VersionStale
                        VersionCompatibility.UnknownCurrentVersion ->
                            PageObservationStatus.Uncertain(result.score)
                    }
                    ScreenMatchStatus.Uncertain -> PageObservationStatus.Uncertain(result.score)
                    ScreenMatchStatus.Mismatch -> PageObservationStatus.Mismatch
                }
            }
        }
    }

    private fun com.xisha.guojing.model.TutorialTransition.isLowRiskTrial(): Boolean =
        riskLevel != RiskLevel.Financial && riskLevel != RiskLevel.Irreversible

    private fun ObservationState.requestOrNull(): ObservationRequest? = when (this) {
        ObservationState.Idle -> null
        is ObservationState.CapturePaused -> request
        is ObservationState.Waiting -> request
        is ObservationState.Available -> observation.request
    }

    override fun onCleared() {
        observationPort.stop()
        overlayPort.hide()
        super.onCleared()
    }

    companion object {
        fun factory(
            graphId: String,
            repository: TutorialDetailRepository,
            observationPort: ScreenObservationPort = DisabledScreenObservationPort,
            overlayPort: GuidanceOverlayPort = DisabledGuidanceOverlayPort,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                TutorialDetailViewModel(graphId, repository, observationPort, overlayPort)
            }
        }

        private const val REQUIRED_TARGET_MATCHES = 2
    }
}
