package com.xisha.guojing.ui.catalog

import com.xisha.guojing.model.TutorialSummary

sealed interface TutorialCatalogUiState {
    data object Loading : TutorialCatalogUiState

    data class Content(
        val tutorials: List<TutorialSummary>,
    ) : TutorialCatalogUiState

    data object Empty : TutorialCatalogUiState

    data object Error : TutorialCatalogUiState
}
