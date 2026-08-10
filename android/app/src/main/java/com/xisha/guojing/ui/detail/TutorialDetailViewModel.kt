package com.xisha.guojing.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.execution.TutorialExecutionEngine
import com.xisha.guojing.execution.TutorialExecutionStage
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TutorialDetailViewModel(
    private val graphId: String,
    private val repository: TutorialDetailRepository,
) : ViewModel() {
    private val mutableUiState = MutableStateFlow<TutorialDetailUiState>(
        TutorialDetailUiState.Loading,
    )
    val uiState: StateFlow<TutorialDetailUiState> = mutableUiState.asStateFlow()

    private var loadJob: Job? = null
    private var executionEngine: TutorialExecutionEngine? = null

    init {
        load()
    }

    fun retry() {
        load()
    }

    fun startTutorial() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        val engine = TutorialExecutionEngine(content.tutorial.graph)
        executionEngine = engine
        mutableUiState.value = content.copy(
            mode = TutorialDetailMode.Execution(engine.start()),
        )
    }

    fun confirmStepCompleted() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        val execution = content.mode as? TutorialDetailMode.Execution ?: return
        val step = execution.stage as? TutorialExecutionStage.Step ?: return
        val engine = executionEngine ?: return
        mutableUiState.value = content.copy(
            mode = TutorialDetailMode.Execution(engine.advance(step)),
        )
    }

    fun exitExecution() {
        val content = mutableUiState.value as? TutorialDetailUiState.Content ?: return
        executionEngine = null
        mutableUiState.value = content.copy(mode = TutorialDetailMode.Overview)
    }

    private fun load() {
        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            executionEngine = null
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

    companion object {
        fun factory(
            graphId: String,
            repository: TutorialDetailRepository,
        ): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                TutorialDetailViewModel(graphId, repository)
            }
        }
    }
}
