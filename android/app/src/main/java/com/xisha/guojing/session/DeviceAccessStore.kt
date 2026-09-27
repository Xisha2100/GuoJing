package com.xisha.guojing.session

import android.content.Context
import com.xisha.guojing.model.DeviceAccess
import java.security.SecureRandom
import java.util.Base64
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*

interface DeviceAccessStore {
    suspend fun load(): DeviceAccess?
    suspend fun save(value: DeviceAccess)
}

fun invitedInstallation(invitation: String): DeviceAccess {
    require(invitation.matches(Regex("[A-Za-z0-9_-]{32,128}"))) { "邀请码格式不正确" }
    val secret = ByteArray(32).also { SecureRandom().nextBytes(it) }
    return try {
        DeviceAccess(UUID.randomUUID(), Base64.getUrlEncoder().withoutPadding().encodeToString(secret), invitation)
    } finally {
        secret.fill(0)
    }
}

class EncryptedDeviceAccessStore(context: Context) : DeviceAccessStore {
    private val preferences = context.getSharedPreferences("device-access", Context.MODE_PRIVATE)
    private val cipher = AndroidSessionCipher()

    override suspend fun load(): DeviceAccess? = withContext(Dispatchers.IO) {
        val encrypted = preferences.getString("credential", null) ?: return@withContext null
        runCatching {
            val root = Json.parseToJsonElement(requireNotNull(cipher.decrypt(encrypted))).jsonObject
            DeviceAccess(
                UUID.fromString(root.getValue("installation_id").jsonPrimitive.content),
                root.getValue("secret").jsonPrimitive.content,
                root["invitation"]?.jsonPrimitive?.contentOrNull,
                root["device_id"]?.jsonPrimitive?.contentOrNull?.let(UUID::fromString),
                root["expires_at"]?.jsonPrimitive?.contentOrNull,
            )
        }.getOrElse {
            check(preferences.edit().remove("credential").commit())
            null
        }
    }

    override suspend fun save(value: DeviceAccess) = withContext(Dispatchers.IO) {
        val json = buildJsonObject {
            put("installation_id", value.installationId.toString())
            put("secret", value.secret)
            put("invitation", value.invitation)
            put("device_id", value.deviceId?.toString())
            put("expires_at", value.expiresAt)
        }.toString()
        check(preferences.edit().putString("credential", cipher.encrypt(json)).commit())
    }
}
