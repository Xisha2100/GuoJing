package com.xisha.guojing.privacy

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NormalizedRedactionTest {
    @Test
    fun drag_is_reordered_and_clamped_to_image_bounds() {
        val redaction = requireNotNull(
            NormalizedRedaction.fromDrag(
                startX = 1.2f,
                startY = 0.8f,
                endX = -0.2f,
                endY = 0.1f,
            ),
        )

        assertEquals(0f, redaction.left, 0.001f)
        assertEquals(0.1f, redaction.top, 0.001f)
        assertEquals(1f, redaction.right, 0.001f)
        assertEquals(0.8f, redaction.bottom, 0.001f)
    }

    @Test
    fun tiny_drag_is_rejected_as_an_accidental_touch() {
        assertNull(
            NormalizedRedaction.fromDrag(
                startX = 0.5f,
                startY = 0.5f,
                endX = 0.51f,
                endY = 0.51f,
            ),
        )
    }
}
