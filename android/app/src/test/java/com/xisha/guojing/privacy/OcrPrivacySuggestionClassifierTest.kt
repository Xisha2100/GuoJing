package com.xisha.guojing.privacy

import com.xisha.guojing.observation.NormalizedScreenBounds
import com.xisha.guojing.observation.OcrTextBlock
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OcrPrivacySuggestionClassifierTest {
    private val classifier = OcrPrivacySuggestionClassifier()
    private val bounds = NormalizedScreenBounds(0.1, 0.2, 0.8, 0.3)

    @Test
    fun classifies_sensitive_patterns_without_returning_original_text() {
        val suggestions = classifier.classify(
            listOf(
                OcrTextBlock("电话 13800138000", 0.9, bounds),
                OcrTextBlock("余额 ￥38.50", 0.8, bounds.copy(top = 0.4, bottom = 0.5)),
                OcrTextBlock("普通教程文字", 1.0, bounds.copy(top = 0.6, bottom = 0.7)),
            ),
        )

        assertEquals(
            listOf(SensitiveTextKind.Phone, SensitiveTextKind.Balance),
            suggestions.map(OcrPrivacySuggestion::kind),
        )
        assertTrue(suggestions.all { suggestion ->
            suggestion.toString().contains("13800138000").not()
        })
        assertEquals(PrivacySuggestionDecision.Pending, suggestions.first().decision)
    }

    @Test
    fun labels_can_create_a_hint_even_when_the_value_is_not_fully_read() {
        val suggestions = classifier.classify(
            listOf(
                OcrTextBlock("收货地址：北京市", 0.95, bounds),
                OcrTextBlock("订单号", 0.95, bounds.copy(top = 0.4, bottom = 0.5)),
            ),
        )

        assertEquals(
            listOf(SensitiveTextKind.Address, SensitiveTextKind.OrderNumber),
            suggestions.map(OcrPrivacySuggestion::kind),
        )
    }

    @Test
    fun invalid_or_tiny_bounds_are_not_suggested() {
        val suggestions = classifier.classify(
            listOf(
                OcrTextBlock(
                    "13800138000",
                    0.99,
                    NormalizedScreenBounds(0.1, 0.2, 0.105, 0.3),
                ),
                OcrTextBlock("13800138000", 0.99, null),
            ),
        )

        assertTrue(suggestions.isEmpty())
    }
}
