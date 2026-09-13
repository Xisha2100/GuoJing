package com.xisha.guojing.speech

import org.junit.Assert.*
import org.junit.Test

class SpeechSegmentsTest {
    @Test
    fun preserves_every_character_in_long_unicode_instruction() {
        val text = "点击右上角的设置按钮，不要点击删除。".repeat(15) + "😀完成"
        val segments = speechSegments(text)
        assertEquals(text, segments.joinToString("") { text.substring(it.start, it.end) })
        segments.forEach {
            assertTrue(text.codePointCount(it.start, it.end) <= 14)
            assertFalse(Character.isLowSurrogate(text[it.start]))
        }
    }

    @Test
    fun punctuation_provides_natural_fallback_boundaries() {
        val text = "点击设置，然后查看页面。"
        assertEquals(listOf("点击设置，", "然后查看页面。"),
            speechSegments(text).map { text.substring(it.start, it.end) })
        assertTrue(speechSegments("").isEmpty())
    }
}
