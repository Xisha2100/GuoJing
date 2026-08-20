package com.xisha.guojing.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.execution.TutorialExecutionEngine
import com.xisha.guojing.execution.TutorialExecutionStage
import com.xisha.guojing.model.TutorialGraph
import com.xisha.guojing.observation.DisabledScreenObservationPort
import com.xisha.guojing.observation.ObservationRequest
import com.xisha.guojing.observation.ObservationSharingPolicy
import com.xisha.guojing.observation.ObservationState
import com.xisha.guojing.observation.ScreenMatchStatus
import com.xisha.guojing.observation.ScreenObservationPort
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
) : ViewModel() {
    private val mutableUiState = MutableStateFlow<TutorialDetailUiState>(
        TutorialDetailUiState.Loading,
    )
    val uiState: StateFlow<TutorialDetailUiState> = mutableUiState.asStateFlow()

    private var loadJob: Job? = null
    private var executionEngine: TutorialExecutionEngine? = null

    init {
        observePageEvidence()
        load()
    }

    fun retry() {
        load()
    }

    fun startTutorial() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        val engine = TutorialExecutionEngine(content.tutorial.graph)
        executionEngine = engine
        val stage = engine.start()
        mutableUiState.value = content.copy(
            mode = TutorialDetailMode.Execution(stage),
        )
        observeStage(content.tutorial.graph, stage)
    }

    fun confirmStepCompleted() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        val execution = content.mode as? TutorialDetailMode.Execution ?: return
        val step = execution.stage as? TutorialExecutionStage.Step ?: return
        val engine = executionEngine ?: return
        val nextStage = engine.advance(step)
        mutableUiState.value = content.copy(mode = TutorialDetailMode.Execution(nextStage))
        observeStage(content.tutorial.graph, nextStage)
    }

    fun exitExecution() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        executionEngine = null
        observationPort.stop()
        mutableUiState.value = content.copy(mode = TutorialDetailMode.Overview)
    }

    private fun load() {
        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            executionEngine = null
            observationPort.stop()
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
                val status = observationState.toPageStatus(
                    graph = content.tutorial.graph,
                    stage = execution.stage,
                )
                mutableUiState.value = content.copy(
                    mode = execution.copy(pageObservation = status),
                )
            }
        }
    }

    private fun observeStage(graph: TutorialGraph, stage: TutorialExecutionStage) {
        val node = stage.node
        if (stage is TutorialExecutionStage.Step) {
            observationPort.observe(
                ObservationRequest(
                    graphId = graph.graphId,
                    nodeId = node.nodeId,
                    targetPackageName = graph.recordedApp.packageName,
                    anchors = node.anchors,
                    privacyMode = node.privacyMode,
                ),
            )
        } else {
            observationPort.stop()
        }
    }

    private fun ObservationState.toPageStatus(
        graph: TutorialGraph,
        stage: TutorialExecutionStage,
    ): PageObservationStatus = when (this) {
        ObservationState.Idle -> PageObservationStatus.NotStarted
        is ObservationState.CapturePaused -> PageObservationStatus.CapturePaused
        is ObservationState.Waiting -> PageObservationStatus.WaitingForTargetApp
        is ObservationState.Available -> {
            if (observation.request.nodeId != stage.node.nodeId) {
                PageObservationStatus.WaitingForTargetApp
            } else {
                val result = matchScreen(graph, stage.node, observation)
                when (result.status) {
                    ScreenMatchStatus.Matched -> PageObservationStatus.Matched(
                        score = result.score,
                        localOnly = observation.sharingPolicy ==
                            ObservationSharingPolicy.LocalOnly,
                    )
                    ScreenMatchStatus.Uncertain -> PageObservationStatus.Uncertain(result.score)
                    ScreenMatchStatus.Mismatch -> PageObservationStatus.Mismatch
                }
            }
        }
    }

    companion object {
        fun factory(
            graphId: String,
            repository: TutorialDetailRepository,
            observationPort: ScreenObservationPort = DisabledScreenObservationPort,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                TutorialDetailViewModel(graphId, repository, observationPort)
            }
        }
    }
}
