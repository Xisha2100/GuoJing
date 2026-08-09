package com.xisha.guojing.ui.catalog

import com.xisha.guojing.data.TutorialCatalogRepository
import com.xisha.guojing.model.TutorialSummary
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class TutorialCatalogViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun exposes_content_after_successful_load() = runTest(mainDispatcherRule.dispatcher) {
        val viewModel = TutorialCatalogViewModel(
            TutorialCatalogRepository { listOf(TUTORIAL) },
        )

        assertEquals(TutorialCatalogUiState.Loading, viewModel.uiState.value)
        advanceUntilIdle()

        assertEquals(
            TutorialCatalogUiState.Content(listOf(TUTORIAL)),
            viewModel.uiState.value,
        )
    }

    @Test
    fun exposes_empty_when_backend_has_no_published_tutorials() =
        runTest(mainDispatcherRule.dispatcher) {
            val viewModel = TutorialCatalogViewModel(
                TutorialCatalogRepository { emptyList() },
            )

            advanceUntilIdle()

            assertEquals(TutorialCatalogUiState.Empty, viewModel.uiState.value)
        }

    @Test
    fun retry_recovers_after_failure() = runTest(mainDispatcherRule.dispatcher) {
        var attempt = 0
        val viewModel = TutorialCatalogViewModel(
            TutorialCatalogRepository {
                attempt += 1
                if (attempt == 1) error("offline") else listOf(TUTORIAL)
            },
        )
        advanceUntilIdle()
        assertEquals(TutorialCatalogUiState.Error, viewModel.uiState.value)

        viewModel.retry()
        advanceUntilIdle()

        assertEquals(
            TutorialCatalogUiState.Content(listOf(TUTORIAL)),
            viewModel.uiState.value,
        )
    }

    private companion object {
        val TUTORIAL = TutorialSummary(
            graphId = "wechat-call",
            title = "微信打电话",
            packageName = "com.tencent.mm",
            recordedVersionName = "8.0.60",
            recordedVersionCode = 2800,
            revisionNumber = 3,
            publishedAt = "2026-08-09T07:00:00Z",
        )
    }
}
