package com.xisha.guojing.ui.detail

import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.execution.TutorialExecutionStage
import com.xisha.guojing.guidance.GuidanceOverlayCommand
import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.guidance.GuidanceOverlayState
import com.xisha.guojing.observation.AnchorEvidence
import com.xisha.guojing.observation.ObservationRequest
import com.xisha.guojing.observation.ObservationSharingPolicy
import com.xisha.guojing.observation.ObservationState
import com.xisha.guojing.observation.NormalizedScreenBounds
import com.xisha.guojing.observation.ObservedApp
import com.xisha.guojing.observation.ScreenObservation
import com.xisha.guojing.observation.ScreenObservationPort
import com.xisha.guojing.testTutorialDetail
import com.xisha.guojing.ui.catalog.MainDispatcherRule
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
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
    fun execution_requests_current_node_and_maps_sanitized_evidence() =
        runTest(mainDispatcherRule.dispatcher) {
            val observationPort = FakeObservationPort()
            val detail = testTutorialDetail()
            val viewModel = TutorialDetailViewModel(
                graphId = "wechat_open_family_chat",
                repository = TutorialDetailRepository { detail },
                observationPort = observationPort,
            )
            advanceUntilIdle()

            viewModel.startTutorial()

            val request = observationPort.lastRequest!!
            assertEquals("chat_list", request.nodeId)
            assertEquals("com.tencent.mm", request.targetPackageName)

            observationPort.publish(
                ScreenObservation(
                    request = request,
                    app = ObservedApp("com.tencent.mm", "8.0.60", 2600),
                    anchorEvidence = listOf(
                        AnchorEvidence(request.anchors.single().anchorId, 1.0, null),
                    ),
                    structureScore = 1.0,
                    sharingPolicy = ObservationSharingPolicy.LocalOnly,
                ),
            )
            advanceUntilIdle()

            val content = viewModel.uiState.value as TutorialDetailUiState.Content
            val execution = content.mode as TutorialDetailMode.Execution
            assertEquals(
                PageObservationStatus.Matched(score = 0.90, localOnly = true),
                execution.pageObservation,
            )
        }

    @Test
    fun matched_source_page_shows_non_touching_guidance_with_anchor_bounds() =
        runTest(mainDispatcherRule.dispatcher) {
            val observationPort = FakeObservationPort()
            val overlayPort = FakeOverlayPort()
            val viewModel = TutorialDetailViewModel(
                graphId = "wechat_open_family_chat",
                repository = TutorialDetailRepository { testTutorialDetail() },
                observationPort = observationPort,
                overlayPort = overlayPort,
            )
            advanceUntilIdle()
            viewModel.startTutorial()
            val bounds = NormalizedScreenBounds(0.1, 0.2, 0.7, 0.3)

            observationPort.publish(matchingObservation(observationPort.lastRequest!!, bounds))
            advanceUntilIdle()

            assertEquals(bounds, overlayPort.lastCommand?.targetBounds)
            assertEquals("点击“家人”聊天", overlayPort.lastCommand?.instruction)
        }

    @Test
    fun observed_mode_requires_two_consecutive_target_matches_before_advancing() =
        runTest(mainDispatcherRule.dispatcher) {
            val observationPort = FakeObservationPort()
            val viewModel = TutorialDetailViewModel(
                graphId = "wechat_open_family_chat",
                repository = TutorialDetailRepository { testTutorialDetail() },
                observationPort = observationPort,
            )
            advanceUntilIdle()
            viewModel.startTutorial()

            viewModel.confirmStepCompleted(requirePageVerification = true)
            val targetRequest = observationPort.lastRequest!!
            assertEquals("conversation", targetRequest.nodeId)

            observationPort.publish(matchingObservation(targetRequest))
            advanceUntilIdle()
            var execution = currentExecution(viewModel)
            assertTrue(execution.stage is TutorialExecutionStage.Step)
            assertEquals(
                TransitionVerificationStatus.CheckingTarget(1, 2),
                execution.transitionVerification,
            )

            observationPort.publish(matchingObservation(targetRequest))
            advanceUntilIdle()
            execution = currentExecution(viewModel)
            assertTrue(execution.stage is TutorialExecutionStage.Completed)
        }

    @Test
    fun changed_app_version_requires_target_evidence_before_advancing() =
        runTest(mainDispatcherRule.dispatcher) {
            val observationPort = FakeObservationPort()
            val viewModel = TutorialDetailViewModel(
                graphId = "wechat_open_family_chat",
                repository = TutorialDetailRepository { testTutorialDetail() },
                observationPort = observationPort,
            )
            advanceUntilIdle()
            viewModel.startTutorial()
            val sourceRequest = observationPort.lastRequest!!

            observationPort.publish(matchingObservation(sourceRequest, versionCode = 2601))
            advanceUntilIdle()
            assertTrue(
                currentExecution(viewModel).pageObservation is PageObservationStatus.VersionChanged,
            )

            viewModel.confirmStepCompleted()
            val targetRequest = observationPort.lastRequest!!
            assertEquals("conversation", targetRequest.nodeId)
            assertTrue(currentExecution(viewModel).stage is TutorialExecutionStage.Step)

            observationPort.publish(matchingObservation(targetRequest, versionCode = 2601))
            advanceUntilIdle()
            assertTrue(currentExecution(viewModel).stage is TutorialExecutionStage.Step)
            observationPort.publish(matchingObservation(targetRequest, versionCode = 2601))
            advanceUntilIdle()
            assertTrue(currentExecution(viewModel).stage is TutorialExecutionStage.Completed)
        }

    @Test
    fun uncertain_target_never_advances_or_encourages_a_repeat() =
        runTest(mainDispatcherRule.dispatcher) {
            val observationPort = FakeObservationPort()
            val viewModel = TutorialDetailViewModel(
                graphId = "wechat_open_family_chat",
                repository = TutorialDetailRepository { testTutorialDetail() },
                observationPort = observationPort,
            )
            advanceUntilIdle()
            viewModel.startTutorial()
            viewModel.confirmStepCompleted(requirePageVerification = true)
            val targetRequest = observationPort.lastRequest!!

            observationPort.publish(matchingObservation(targetRequest, confidence = 0.0))
            advanceUntilIdle()

            val execution = currentExecution(viewModel)
            assertTrue(execution.stage is TutorialExecutionStage.Step)
            assertEquals(
                TransitionVerificationStatus.TargetUncertain,
                execution.transitionVerification,
            )
        }

    @Test
    fun mismatched_target_package_never_advances() = runTest(mainDispatcherRule.dispatcher) {
        val observationPort = FakeObservationPort()
        val viewModel = TutorialDetailViewModel(
            graphId = "wechat_open_family_chat",
            repository = TutorialDetailRepository { testTutorialDetail() },
            observationPort = observationPort,
        )
        advanceUntilIdle()
        viewModel.startTutorial()
        viewModel.confirmStepCompleted(requirePageVerification = true)
        val targetRequest = observationPort.lastRequest!!

        observationPort.publish(
            matchingObservation(targetRequest, appPackage = "com.example.wrong"),
        )
        advanceUntilIdle()

        val execution = currentExecution(viewModel)
        assertTrue(execution.stage is TutorialExecutionStage.Step)
        assertEquals(
            TransitionVerificationStatus.TargetMismatch,
            execution.transitionVerification,
        )
    }

    @Test
    fun capture_paused_target_never_advances() = runTest(mainDispatcherRule.dispatcher) {
        val observationPort = FakeObservationPort()
        val viewModel = TutorialDetailViewModel(
            graphId = "wechat_open_family_chat",
            repository = TutorialDetailRepository { testTutorialDetail() },
            observationPort = observationPort,
        )
        advanceUntilIdle()
        viewModel.startTutorial()
        viewModel.confirmStepCompleted(requirePageVerification = true)
        val targetRequest = observationPort.lastRequest!!

        observationPort.pause(targetRequest)
        advanceUntilIdle()

        val execution = currentExecution(viewModel)
        assertTrue(execution.stage is TutorialExecutionStage.Step)
        assertEquals(
            TransitionVerificationStatus.CapturePaused,
            execution.transitionVerification,
        )
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

    private class FakeObservationPort : ScreenObservationPort {
        private val mutableState = MutableStateFlow<ObservationState>(ObservationState.Idle)
        override val state: StateFlow<ObservationState> = mutableState
        var lastRequest: ObservationRequest? = null
        private var sequence = 0L

        override fun observe(request: ObservationRequest) {
            lastRequest = request
            mutableState.value = ObservationState.Waiting(request)
        }

        override fun stop() {
            mutableState.value = ObservationState.Idle
        }

        fun publish(observation: ScreenObservation) {
            sequence += 1
            mutableState.value = ObservationState.Available(sequence, observation)
        }

        fun pause(request: ObservationRequest) {
            mutableState.value = ObservationState.CapturePaused(request)
        }
    }

    private class FakeOverlayPort : GuidanceOverlayPort {
        private val mutableState = MutableStateFlow<GuidanceOverlayState>(
            GuidanceOverlayState.Hidden,
        )
        override val state: StateFlow<GuidanceOverlayState> = mutableState
        var lastCommand: GuidanceOverlayCommand? = null

        override fun show(command: GuidanceOverlayCommand) {
            lastCommand = command
            mutableState.value = GuidanceOverlayState.Visible(1, command)
        }

        override fun hide() {
            mutableState.value = GuidanceOverlayState.Hidden
        }
    }

    private fun matchingObservation(
        request: ObservationRequest,
        bounds: NormalizedScreenBounds? = null,
        confidence: Double = 1.0,
        appPackage: String = "com.tencent.mm",
        versionCode: Long = 2600,
    ) = ScreenObservation(
        request = request,
        app = ObservedApp(appPackage, "8.0.60", versionCode),
        anchorEvidence = listOf(
            AnchorEvidence(request.anchors.single().anchorId, confidence, bounds),
        ),
        structureScore = if (confidence >= 0.80) 1.0 else 0.0,
        sharingPolicy = ObservationSharingPolicy.LocalOnly,
    )

    private fun currentExecution(viewModel: TutorialDetailViewModel): TutorialDetailMode.Execution {
        val content = viewModel.uiState.value as TutorialDetailUiState.Content
        return content.mode as TutorialDetailMode.Execution
    }
}
