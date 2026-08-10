package com.xisha.guojing.ui.detail

import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.execution.TutorialExecutionStage
import com.xisha.guojing.testTutorialDetail
import com.xisha.guojing.ui.catalog.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class TutorialDetailViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun loads_requested_tutorial_into_overview() = runTest(mainDispatcherRule.dispatcher) {
        var requestedGraphId: String? = null
        val viewModel = TutorialDetailViewModel(
            graphId = "wechat_open_family_chat",
            repository = TutorialDetailRepository { graphId ->
                requestedGraphId = graphId
                testTutorialDetail()
            },
        )

        advanceUntilIdle()

        assertEquals("wechat_open_family_chat", requestedGraphId)
        val content = viewModel.uiState.value as TutorialDetailUiState.Content
        assertEquals(TutorialDetailMode.Overview, content.mode)
    }

    @Test
    fun start_and_confirmation_advance_execution() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = TutorialDetailViewModel(
            graphId = "wechat_open_family_chat",
            repository = TutorialDetailRepository { testTutorialDetail() },
        )
        advanceUntilIdle()

        viewModel.startTutorial()
        val running = viewModel.uiState.value as TutorialDetailUiState.Content
        assertTrue(
            (running.mode as TutorialDetailMode.Execution).stage
                is TutorialExecutionStage.Step,
        )

        viewModel.confirmStepCompleted()

        val completed = viewModel.uiState.value as TutorialDetailUiState.Content
        assertTrue(
            (completed.mode as TutorialDetailMode.Execution).stage
                is TutorialExecutionStage.Completed,
        )
    }

    @Test
    fun exit_execution_returns_to_overview() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = TutorialDetailViewModel(
            graphId = "wechat_open_family_chat",
            repository = TutorialDetailRepository { testTutorialDetail() },
        )
        advanceUntilIdle()
        viewModel.startTutorial()

        viewModel.exitExecution()

        val content = viewModel.uiState.value as TutorialDetailUiState.Content
        assertEquals(TutorialDetailMode.Overview, content.mode)
    }

    @Test
    fun retry_recovers_after_loading_failure() = runTest(mainDispatcherRule.dispatcher) {
        var attempt = 0
        val viewModel = TutorialDetailViewModel(
            graphId = "wechat_open_family_chat",
            repository = TutorialDetailRepository {
                attempt += 1
                if (attempt == 1) error("offline") else testTutorialDetail()
            },
        )
        advanceUntilIdle()
        assertEquals(TutorialDetailUiState.Error, viewModel.uiState.value)

        viewModel.retry()
        advanceUntilIdle()

        assertTrue(viewModel.uiState.value is TutorialDetailUiState.Content)
    }
}
