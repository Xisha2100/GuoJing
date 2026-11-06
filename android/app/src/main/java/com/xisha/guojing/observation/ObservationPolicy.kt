package com.xisha.guojing.observation

import kotlinx.coroutines.delay

/** Metadata only: never inspect node contents or initiate another capture. */
internal object ObservationPolicy {
    suspend fun awaitReady(isReady: () -> Boolean): Boolean {
        repeat(40) {
            if (isReady()) return true
            delay(50)
        }
        return false
    }

    fun invalidates(targetEvent: Boolean, pageChanged: Boolean, geometryChanged: Boolean): Boolean =
        geometryChanged || (targetEvent && pageChanged)

    fun captureReady(targetMatches: Boolean, inputVisible: Boolean, locked: Boolean): Boolean =
        targetMatches && !inputVisible && !locked
}
