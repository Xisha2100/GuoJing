package com.xisha.guojing.ui.catalog

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.xisha.guojing.data.TutorialCatalogRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class TutorialCatalogViewModel(
    private val repository: TutorialCatalogRepository,
) : ViewModel() {
    private val mutableUiState = MutableStateFlow<TutorialCatalogUiState>(
        TutorialCatalogUiState.Loading,
    )
    val uiState: StateFlow<TutorialCatalogUiState> = mutableUiState.asStateFlow()

    private var loadJob: Job? = null

    init {
        load()
    }

    fun retry() {
        load()
    }

    private fun load() {
        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            mutableUiState.value = TutorialCatalogUiState.Loading
            mutableUiState.value = try {
                val tutorials = repository.getPublishedTutorials()
                if (tutorials.isEmpty()) {
                    TutorialCatalogUiState.Empty
                } else {
                    TutorialCatalogUiState.Content(tutorials)
                }
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                TutorialCatalogUiState.Error
            }
        }
    }

    companion object {
        fun factory(repository: TutorialCatalogRepository): ViewModelProvider.Factory =
            viewModelFactory {
                initializer {
                    TutorialCatalogViewModel(repository)
                }
            }
    }
}
