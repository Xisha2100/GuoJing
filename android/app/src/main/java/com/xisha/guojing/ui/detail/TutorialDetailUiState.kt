package com.xisha.guojing.ui.detail

import com.xisha.guojing.execution.TutorialExecutionStage
import com.xisha.guojing.model.PublishedTutorialDetail

sealed interface TutorialDetailUiState {
    data object Loading : TutorialDetailUiState

    data object Error : TutorialDetailUiState

    data class Content(
        val tutorial: PublishedTutorialDetail,
        val mode: TutorialDetailMode = TutorialDetailMode.Overview,
    ) : TutorialDetailUiState
}

sealed interface TutorialDetailMode {
    data object Overview : TutorialDetailMode

    data class Execution(
        val stage: TutorialExecutionStage,
    ) : TutorialDetailMode
}
