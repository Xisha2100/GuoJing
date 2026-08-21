package com.xisha.guojing.observation

import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.testNode
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessibilityObservationCoordinatorTest {
    @After
    fun resetCoordinator() {
        AccessibilityObservationCoordinator.stop()
    }

    @Test
    fun capture_paused_never_enters_waiting_state() {
        AccessibilityObservationCoordinator.observe(request(PrivacyMode.CapturePaused))

        assertTrue(
            AccessibilityObservationCoordinator.state.value is ObservationState.CapturePaused,
        )
    }

    @Test
    fun stale_observation_cannot_replace_active_request() {
        val active = request(PrivacyMode.LocalOnly)
        AccessibilityObservationCoordinator.observe(active)
        val stale = observation(active.copy(nodeId = "old_node"))

        AccessibilityObservationCoordinator.publish(stale)

        assertEquals(ObservationState.Waiting(active), AccessibilityObservationCoordinator.state.value)
    }

    @Test
    fun matching_observation_is_published_in_memory() {
        val request = request(PrivacyMode.LocalOnly)
        val observation = observation(request)
        AccessibilityObservationCoordinator.observe(request)

        AccessibilityObservationCoordinator.publish(observation)

        assertEquals(
            ObservationState.Available(sequence = 1, observation = observation),
            AccessibilityObservationCoordinator.state.value,
        )
    }

    private fun request(privacyMode: PrivacyMode): ObservationRequest {
        val node = testNode("chat_list")
        return ObservationRequest(
            graphId = "wechat_open_family_chat",
            nodeId = node.nodeId,
            targetPackageName = "com.tencent.mm",
            anchors = node.anchors,
            privacyMode = privacyMode,
        )
    }

    private fun observation(request: ObservationRequest) = ScreenObservation(
        request = request,
        app = ObservedApp("com.tencent.mm", "8.0.60", 2600),
        anchorEvidence = emptyList(),
        structureScore = 0.0,
        sharingPolicy = ObservationSharingPolicy.LocalOnly,
    )
}
