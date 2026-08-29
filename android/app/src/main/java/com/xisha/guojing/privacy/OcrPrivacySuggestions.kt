package com.xisha.guojing.privacy

import com.xisha.guojing.observation.OcrTextBlock
import com.xisha.guojing.observation.NormalizedScreenBounds
import java.util.Locale

enum class SensitiveTextKind(val displayName: String) {
    Phone("电话号码"),
    Email("邮箱地址"),
    IdentityNumber("身份证号"),
    BankCard("银行卡号"),
    Address("姓名、联系人或地址"),
    Balance("余额或金额"),
    OrderNumber("订单号或物流信息"),
    VerificationCode("验证码"),
}

enum class PrivacySuggestionDecision {
    Pending,
    Accepted,
    Rejected,
}

/** Contains no OCR text; the original line is consumed by the classifier. */
data class OcrPrivacySuggestion(
    val id: String,
    val kind: SensitiveTextKind,
    val bounds: NormalizedRedaction,
    val confidence: Double,
    val decision: PrivacySuggestionDecision = PrivacySuggestionDecision.Pending,
)

data class OcrPrivacyClassification(
    val suggestions: List<OcrPrivacySuggestion>,
    val truncated: Boolean,
)

/**
 * Conservative, local-only privacy hints. These are suggestions rather than proof that a
 * region is sensitive; the user must accept or reject every hint before sanitization.
 */
class OcrPrivacySuggestionClassifier {
    fun classify(blocks: List<OcrTextBlock>): List<OcrPrivacySuggestion> =
        classifyDetailed(blocks).suggestions

    fun classifyDetailed(blocks: List<OcrTextBlock>): OcrPrivacyClassification {
        val allSuggestions = blocks
        .mapNotNullIndexed { index, block ->
            val bounds = block.normalizedBounds?.toRedaction() ?: return@mapNotNullIndexed null
            val classification = classifyText(block.text) ?: return@mapNotNullIndexed null
            OcrPrivacySuggestion(
                id = "ocr-suggestion-$index",
                kind = classification.kind,
                bounds = bounds,
                confidence = (classification.confidence * block.confidence).coerceIn(0.0, 1.0),
            )
        }
        .distinctBy { suggestion ->
            listOf(
                suggestion.kind,
                suggestion.bounds.left,
                suggestion.bounds.top,
                suggestion.bounds.right,
                suggestion.bounds.bottom,
            )
        }
        return OcrPrivacyClassification(
            suggestions = allSuggestions.take(MAX_SUGGESTIONS),
            truncated = allSuggestions.size > MAX_SUGGESTIONS,
        )
    }

    private fun classifyText(value: String): Classification? {
        val text = value.trim()
        val compact = text.lowercase(Locale.ROOT).replace(WHITESPACE, "")
        return when {
            EMAIL.matches(compact) -> Classification(SensitiveTextKind.Email, 0.98)
            IDENTITY_NUMBER.containsMatchIn(compact) ->
                Classification(SensitiveTextKind.IdentityNumber, 0.98)
            PHONE.containsMatchIn(compact) -> Classification(SensitiveTextKind.Phone, 0.97)
            BANK_CARD.containsMatchIn(compact) ->
                Classification(SensitiveTextKind.BankCard, 0.96)
            VERIFICATION_LABEL.containsMatchIn(text) && DIGITS.containsMatchIn(compact) ->
                Classification(SensitiveTextKind.VerificationCode, 0.94)
            BALANCE_LABEL.containsMatchIn(text) && DIGITS.containsMatchIn(compact) ->
                Classification(SensitiveTextKind.Balance, 0.91)
            ORDER_LABEL.containsMatchIn(text) ->
                Classification(SensitiveTextKind.OrderNumber, 0.88)
            ADDRESS_LABEL.containsMatchIn(text) ->
                Classification(SensitiveTextKind.Address, 0.86)
            else -> null
        }
    }

    private data class Classification(
        val kind: SensitiveTextKind,
        val confidence: Double,
    )

    private fun NormalizedScreenBounds.toRedaction(): NormalizedRedaction? =
        NormalizedRedaction.fromDrag(
            startX = left.toFloat(),
            startY = top.toFloat(),
            endX = right.toFloat(),
            endY = bottom.toFloat(),
            minimumDimension = MINIMUM_SUGGESTION_DIMENSION,
        )

    private companion object {
        val WHITESPACE = Regex("\\s+")
        val EMAIL = Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")
        val IDENTITY_NUMBER = Regex("(?<!\\d)\\d{17}[0-9x](?!\\d)", RegexOption.IGNORE_CASE)
        val PHONE = Regex("(?<!\\d)1[3-9]\\d{9}(?!\\d)")
        val BANK_CARD = Regex("(?<!\\d)\\d{16,19}(?!\\d)")
        val DIGITS = Regex("\\d+")
        val VERIFICATION_LABEL = Regex("验证码|校验码|动态码")
        val BALANCE_LABEL = Regex("余额|可用金额|账户金额|¥|￥|元")
        val ORDER_LABEL = Regex("订单|快递|物流|运单|包裹")
        val ADDRESS_LABEL = Regex("姓名|联系人|收货人|地址|电话|手机")
        const val MINIMUM_SUGGESTION_DIMENSION = 0.01f
        const val MAX_SUGGESTIONS = 20
    }
}

private inline fun <T, R> Iterable<T>.mapNotNullIndexed(
    transform: (index: Int, T) -> R?,
): List<R> {
    val result = ArrayList<R>()
    forEachIndexed { index, value ->
        transform(index, value)?.let(result::add)
    }
    return result
}
