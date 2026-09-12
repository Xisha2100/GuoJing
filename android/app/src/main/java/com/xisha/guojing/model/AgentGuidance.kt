package com.xisha.guojing.model

import java.util.UUID

data class TargetApp(
    val packageName: String,
    val label: String,
)

data class NormalizedTarget(
    val left: Double,
    val top: Double,
    val right: Double,
    val bottom: Double,
) {
    init {
        require(listOf(left, top, right, bottom).all { it in 0.0..1.0 })
        require(left < right && top < bottom)
    }
}

enum class GuidanceStatus(val wireValue: String) {
    Continue("continue"),
    Completed("completed"),
    CannotDetermine("cannot_determine");

    companion object {
        fun parse(value: String): GuidanceStatus = entries.firstOrNull {
            it.wireValue == value
        } ?: throw AgentProtocolException("Unknown guidance status")
    }
}

data class GuidanceDecision(
    val status: GuidanceStatus,
    val instruction: String?,
    val target: NormalizedTarget?,
    val confidence: Double,
) {
    init {
        require(confidence in 0.0..1.0)
        when (status) {
            GuidanceStatus.Continue -> {
                require(!instruction.isNullOrBlank())
                require(instruction.length <= MAX_INSTRUCTION_LENGTH)
                require(target != null)
                require(confidence >= MIN_GUIDANCE_CONFIDENCE)
            }

            GuidanceStatus.Completed,
            GuidanceStatus.CannotDetermine,
            -> {
                require(target == null)
                require(instruction == null || instruction.length <= MAX_INSTRUCTION_LENGTH)
            }
        }
    }

    private companion object {
        const val MIN_GUIDANCE_CONFIDENCE = 0.70
        const val MAX_INSTRUCTION_LENGTH = 300
    }
}

enum class AgentRunStatus(val wireValue: String) {
    Queued("queued"),
    Running("running"),
    Completed("completed"),
    Failed("failed"),
    Cancelled("cancelled");

    val isTerminal: Boolean
        get() = this in setOf(Completed, Failed, Cancelled)

    companion object {
        fun parse(value: String): AgentRunStatus = entries.firstOrNull {
            it.wireValue == value
        } ?: throw AgentProtocolException("Unknown run status")
    }
}

data class AgentSessionHandle(
    val sessionId: UUID,
    val accessToken: String,
)

data class AgentRunAccepted(
    val runId: UUID,
    val status: AgentRunStatus,
    val eventsEndpoint: String,
)

data class AgentRunSnapshot(
    val runId: UUID,
    val sessionId: UUID,
    val status: AgentRunStatus,
    val result: GuidanceDecision?,
    val errorCode: String?,
    val retryable: Boolean,
)

class CapturedScreen(
    val jpegBytes: ByteArray,
    val width: Int,
    val height: Int,
    val displayWidth: Int,
    val displayHeight: Int,
    val rotation: Int,
) {
    init {
        require(jpegBytes.isNotEmpty())
        require(width > 0 && height > 0)
        require(displayWidth > 0 && displayHeight > 0)
    }

    fun erase() {
        jpegBytes.fill(0)
    }
}

class AgentProtocolException(message: String) : IllegalArgumentException(message)
