package com.xisha.guojing.observation

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertTrue
import org.junit.Assert.assertFalse
import org.junit.Test

class ObservationPolicyTest {
    @Test fun slow_keyboard_waits_for_observed_disappearance() = runTest {
        var checks = 0
        assertTrue(ObservationPolicy.awaitReady { ++checks >= 15 })
        assertTrue(checks == 15)
    }

    @Test fun stuck_keyboard_times_out_without_granting_capture() = runTest {
        assertFalse(ObservationPolicy.awaitReady { false })
    }

    @Test fun page_and_geometry_changes_invalidate_but_own_overlay_events_do_not() {
        assertTrue(ObservationPolicy.invalidates(true, true, false))
        assertTrue(ObservationPolicy.invalidates(false, false, true))
        assertFalse(ObservationPolicy.invalidates(false, true, false))
    }
    @Test fun capture_requires_closed_input_matching_target_and_unlocked_display() {
        assertTrue(ObservationPolicy.captureReady(true, false, false))
        assertFalse(ObservationPolicy.captureReady(true, true, false))
        assertFalse(ObservationPolicy.captureReady(false, false, false))
        assertFalse(ObservationPolicy.captureReady(true, false, true))
    }
}
