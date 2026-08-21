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
        val pageObservation: PageObservationStatus = PageObservationStatus.NotStarted,
        val transitionVerification: TransitionVerificationStatus =
            TransitionVerificationStatus.Ready,
    ) : TutorialDetailMode
}

sealed interface TransitionVerificationStatus {
    data object Ready : TransitionVerificationStatus

    data class CheckingTarget(
        val matchedObservations: Int,
        val requiredObservations: Int,
    ) : TransitionVerificationStatus

    data object TargetUncertain : TransitionVerificationStatus

    data object TargetMismatch : TransitionVerificationStatus

    data object CapturePaused : TransitionVerificationStatus
}

sealed interface PageObservationStatus {
    data object NotStarted : PageObservationStatus

    data object WaitingForTargetApp : PageObservationStatus

    data object CapturePaused : PageObservationStatus

    data class Matched(
        val score: Double,
        val localOnly: Boolean,
    ) : PageObservationStatus

    data class Uncertain(
        val score: Double,
    ) : PageObservationStatus

    data object Mismatch : PageObservationStatus
}
