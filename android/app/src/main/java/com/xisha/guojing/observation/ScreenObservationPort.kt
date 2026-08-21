package com.xisha.guojing.observation

import com.xisha.guojing.model.PrivacyMode
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

interface ScreenObservationPort {
    val state: StateFlow<ObservationState>

    fun observe(request: ObservationRequest)

    fun stop()
}

object AccessibilityObservationCoordinator : ScreenObservationPort {
    private val mutableState = MutableStateFlow<ObservationState>(ObservationState.Idle)
    private var observationSequence = 0L
    override val state: StateFlow<ObservationState> = mutableState.asStateFlow()

    override fun observe(request: ObservationRequest) {
        mutableState.value = if (request.privacyMode == PrivacyMode.CapturePaused) {
            ObservationState.CapturePaused(request)
        } else {
            ObservationState.Waiting(request)
        }
    }

    override fun stop() {
        observationSequence = 0
        mutableState.value = ObservationState.Idle
    }

    fun activeRequest(): ObservationRequest? = when (val current = mutableState.value) {
        ObservationState.Idle -> null
        is ObservationState.CapturePaused -> current.request
        is ObservationState.Waiting -> current.request
        is ObservationState.Available -> current.observation.request
    }

    fun publish(observation: ScreenObservation) {
        val activeRequest = activeRequest() ?: return
        if (observation.request == activeRequest &&
            activeRequest.privacyMode != PrivacyMode.CapturePaused
        ) {
            observationSequence += 1
            mutableState.value = ObservationState.Available(
                sequence = observationSequence,
                observation = observation,
            )
        }
    }
}

object DisabledScreenObservationPort : ScreenObservationPort {
    private val disabledState = MutableStateFlow<ObservationState>(ObservationState.Idle)
    override val state: StateFlow<ObservationState> = disabledState.asStateFlow()

    override fun observe(request: ObservationRequest) = Unit

    override fun stop() = Unit
}
