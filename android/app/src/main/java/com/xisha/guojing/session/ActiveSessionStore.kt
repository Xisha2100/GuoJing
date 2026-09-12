package com.xisha.guojing.session

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.xisha.guojing.model.GuidanceDecision
import com.xisha.guojing.model.GuidanceStatus
import com.xisha.guojing.model.NormalizedTarget
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put

data class StoredAgentSession(
    val sessionId: UUID,
    val accessToken: String,
    val goal: String,
    val targetPackage: String,
    val targetLabel: String,
    val createdAtEpochSeconds: Long,
    val stepNumber: Int,
    val currentRunId: UUID?,
    val eventsEndpoint: String?,
    val lastDecision: GuidanceDecision?,
    val displayWidth: Int?,
    val displayHeight: Int?,
    val rotation: Int?,
)

interface ActiveSessionStore {
    suspend fun load(): StoredAgentSession?

    suspend fun save(value: StoredAgentSession)

    suspend fun clear()
}

class EncryptedActiveSessionStore(context: Context) : ActiveSessionStore {
    private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val cipher = AndroidSessionCipher()

    override suspend fun load(): StoredAgentSession? = withContext(Dispatchers.IO) {
        val encrypted = preferences.getString(ACTIVE_SESSION, null) ?: return@withContext null
        val plaintext = cipher.decrypt(encrypted) ?: run {
            preferences.edit().remove(ACTIVE_SESSION).apply()
            return@withContext null
        }
        runCatching { decode(plaintext) }.getOrElse {
            preferences.edit().remove(ACTIVE_SESSION).apply()
            null
        }
    }

    override suspend fun save(value: StoredAgentSession) {
        withContext(Dispatchers.IO) {
            preferences.edit()
                .putString(ACTIVE_SESSION, cipher.encrypt(encode(value)))
                .apply()
        }
    }

    override suspend fun clear() {
        withContext(Dispatchers.IO) {
            preferences.edit().remove(ACTIVE_SESSION).apply()
        }
    }

    private fun encode(value: StoredAgentSession): String = buildJsonObject {
        put("session_id", value.sessionId.toString())
        put("access_token", value.accessToken)
        put("goal", value.goal)
        put("target_package", value.targetPackage)
        put("target_label", value.targetLabel)
        put("created_at", value.createdAtEpochSeconds)
        put("step_number", value.stepNumber)
        put("current_run_id", value.currentRunId?.toString())
        put("events_endpoint", value.eventsEndpoint)
        put("display_width", value.displayWidth)
        put("display_height", value.displayHeight)
        put("rotation", value.rotation)
        value.lastDecision?.let { decision ->
            put(
                "last_decision",
                buildJsonObject {
                    put("status", decision.status.wireValue)
                    put("instruction", decision.instruction)
                    put("confidence", decision.confidence)
                    decision.target?.let { target ->
                        put(
                            "target",
                            buildJsonObject {
                                put("left", target.left)
                                put("top", target.top)
                                put("right", target.right)
                                put("bottom", target.bottom)
                            },
                        )
                    } ?: put("target", JsonNull)
                },
            )
        } ?: put("last_decision", JsonNull)
    }.toString()

    private fun decode(value: String): StoredAgentSession {
        val root = Json.parseToJsonElement(value).jsonObject
        val decision = root.objectOrNull("last_decision")?.let { item ->
            GuidanceDecision(
                status = GuidanceStatus.parse(item.string("status")),
                instruction = item.stringOrNull("instruction"),
                target = item.objectOrNull("target")?.let { target ->
                    NormalizedTarget(
                        target.number("left"),
                        target.number("top"),
                        target.number("right"),
                        target.number("bottom"),
                    )
                },
                confidence = item.number("confidence"),
            )
        }
        return StoredAgentSession(
            sessionId = UUID.fromString(root.string("session_id")),
            accessToken = root.string("access_token"),
            goal = root.string("goal"),
            targetPackage = root.string("target_package"),
            targetLabel = root.string("target_label"),
            createdAtEpochSeconds = root["created_at"]!!.jsonPrimitive.long,
            stepNumber = root["step_number"]!!.jsonPrimitive.int,
            currentRunId = root.stringOrNull("current_run_id")?.let(UUID::fromString),
            eventsEndpoint = root.stringOrNull("events_endpoint"),
            lastDecision = decision,
            displayWidth = root.intOrNull("display_width"),
            displayHeight = root.intOrNull("display_height"),
            rotation = root.intOrNull("rotation"),
        )
    }

    private fun JsonObject.string(name: String): String =
        requireNotNull(this[name]).jsonPrimitive.content

    private fun JsonObject.stringOrNull(name: String): String? =
        this[name]?.let { if (it is JsonNull) null else it.jsonPrimitive.content }

    private fun JsonObject.intOrNull(name: String): Int? =
        this[name]?.let { if (it is JsonNull) null else it.jsonPrimitive.int }

    private fun JsonObject.objectOrNull(name: String): JsonObject? =
        this[name]?.let { if (it is JsonNull) null else it.jsonObject }

    private fun JsonObject.number(name: String): Double =
        requireNotNull(this[name]).jsonPrimitive.double

    private companion object {
        const val PREFERENCES = "agent-session"
        const val ACTIVE_SESSION = "active"
    }
}

private class AndroidSessionCipher {
    fun encrypt(value: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(value.toByteArray(StandardCharsets.UTF_8))
        return Base64.encodeToString(cipher.iv + encrypted, Base64.NO_WRAP)
    }

    fun decrypt(value: String): String? = runCatching {
        val payload = Base64.decode(value, Base64.NO_WRAP)
        require(payload.size > GCM_IV_LENGTH)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(
            Cipher.DECRYPT_MODE,
            key(),
            GCMParameterSpec(GCM_TAG_LENGTH, payload.copyOfRange(0, GCM_IV_LENGTH)),
        )
        String(
            cipher.doFinal(payload.copyOfRange(GCM_IV_LENGTH, payload.size)),
            StandardCharsets.UTF_8,
        )
    }.getOrNull()

    private fun key(): SecretKey {
        val store = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).run {
            init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
            generateKey()
        }
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "guojing.agent.session"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_IV_LENGTH = 12
        const val GCM_TAG_LENGTH = 128
    }
}
