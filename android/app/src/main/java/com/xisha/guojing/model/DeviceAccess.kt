package com.xisha.guojing.model

import java.util.UUID

/** Installation secret and invitation are never displayed or logged. */
data class DeviceAccess(
    val installationId: UUID,
    val secret: String,
    val invitation: String?,
    val deviceId: UUID? = null,
    val expiresAt: String? = null,
) {
    val authorization: String? get() = deviceId?.let { "Bearer $it.$secret" }
}

data class DeviceActivation(val deviceId: UUID, val expiresAt: String)
