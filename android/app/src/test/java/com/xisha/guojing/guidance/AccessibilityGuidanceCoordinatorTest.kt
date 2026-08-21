package com.xisha.guojing.guidance

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class AccessibilityGuidanceCoordinatorTest {
    @After
    fun hideOverlay() {
        AccessibilityGuidanceCoordinator.hide()
    }

    @Test
    fun repeated_command_gets_a_new_sequence_for_reshowing_after_app_switch() {
        val command = GuidanceOverlayCommand(
            targetPackageName = "com.tencent.mm",
            stepNumber = 1,
            instruction = "点击家人聊天",
            targetBounds = null,
        )

        AccessibilityGuidanceCoordinator.show(command)
        val first = AccessibilityGuidanceCoordinator.state.value as GuidanceOverlayState.Visible
        AccessibilityGuidanceCoordinator.show(command)
        val second = AccessibilityGuidanceCoordinator.state.value as GuidanceOverlayState.Visible

        assertNotEquals(first.sequence, second.sequence)
        assertEquals(command, second.command)
    }

    @Test
    fun hide_removes_visible_guidance_state() {
        AccessibilityGuidanceCoordinator.show(
            GuidanceOverlayCommand("com.tencent.mm", 1, "点击家人聊天", null),
        )

        AccessibilityGuidanceCoordinator.hide()

        assertEquals(
            GuidanceOverlayState.Hidden,
            AccessibilityGuidanceCoordinator.state.value,
        )
    }
}
