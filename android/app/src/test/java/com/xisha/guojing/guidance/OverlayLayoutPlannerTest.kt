package com.xisha.guojing.guidance

import com.xisha.guojing.observation.NormalizedScreenBounds
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OverlayLayoutPlannerTest {
    private val planner = OverlayLayoutPlanner()

    @Test
    fun target_in_top_half_puts_instruction_card_at_bottom() {
        val layout = planner.plan(
            screenWidth = 1080,
            screenHeight = 2400,
            targetBounds = NormalizedScreenBounds(0.1, 0.1, 0.9, 0.2),
            density = 3f,
        )

        assertTrue(layout.cardRect.top > 1200)
        assertNotNull(layout.targetRect)
        assertTrue(layout.arrowStart!!.y > layout.arrowEnd!!.y)
    }

    @Test
    fun target_in_bottom_half_puts_instruction_card_at_top() {
        val layout = planner.plan(
            screenWidth = 1080,
            screenHeight = 2400,
            targetBounds = NormalizedScreenBounds(0.2, 0.75, 0.8, 0.85),
            density = 3f,
        )

        assertTrue(layout.cardRect.bottom < 1200)
        assertTrue(layout.arrowStart!!.y < layout.arrowEnd!!.y)
    }

    @Test
    fun padded_target_is_clamped_inside_display() {
        val layout = planner.plan(
            screenWidth = 100,
            screenHeight = 200,
            targetBounds = NormalizedScreenBounds(0.0, 0.0, 1.0, 1.0),
            density = 2f,
        )
        val target = requireNotNull(layout.targetRect)

        assertEquals(0f, target.left, 0.001f)
        assertEquals(0f, target.top, 0.001f)
        assertEquals(100f, target.right, 0.001f)
        assertEquals(200f, target.bottom, 0.001f)
    }

    @Test
    fun display_coordinates_are_translated_into_an_inset_overlay_viewport() {
        val layout = planner.plan(
            screenWidth = 1080,
            screenHeight = 2274,
            targetBounds = NormalizedScreenBounds(0.2, 0.25, 0.6, 0.30),
            density = 1f,
            displayWidth = 1080,
            displayHeight = 2400,
            viewportTop = 63,
        )
        val target = requireNotNull(layout.targetRect)

        assertEquals(208f, target.left, 0.001f)
        assertEquals(529f, target.top, 0.001f)
        assertEquals(656f, target.right, 0.001f)
        assertEquals(665f, target.bottom, 0.001f)
    }

    @Test
    fun missing_anchor_still_provides_instruction_card_without_arrow() {
        val layout = planner.plan(1080, 2400, null, 3f)

        assertNull(layout.targetRect)
        assertNull(layout.arrowStart)
        assertNull(layout.arrowEnd)
        assertTrue(layout.cardRect.top > 1200)
    }
}
