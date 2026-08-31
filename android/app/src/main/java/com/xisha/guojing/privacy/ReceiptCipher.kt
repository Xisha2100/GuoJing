package com.xisha.guojing.privacy

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypts the short-lived help receipt before it enters saved instance state. */
interface ReceiptCipher {
    fun encrypt(value: String): String
    fun decrypt(value: String): String?
}

/** Test/default implementation used when no Android keystore is available. */
object PlaintextReceiptCipher : ReceiptCipher {
    override fun encrypt(value: String): String = value

    override fun decrypt(value: String): String = value
}

class AndroidKeystoreReceiptCipher(
    private val alias: String = "guojing.help.receipt",
) : ReceiptCipher {
    override fun encrypt(value: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val iv = cipher.iv
        val encrypted = cipher.doFinal(value.toByteArray(StandardCharsets.UTF_8))
        return Base64.encodeToString(iv + encrypted, Base64.NO_WRAP)
    }

    override fun decrypt(value: String): String? = try {
        val payload = Base64.decode(value, Base64.NO_WRAP)
        require(payload.size > GCM_IV_LENGTH)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(
            Cipher.DECRYPT_MODE,
            key(),
            GCMParameterSpec(GCM_TAG_LENGTH, payload.copyOfRange(0, GCM_IV_LENGTH)),
        )
        String(cipher.doFinal(payload.copyOfRange(GCM_IV_LENGTH, payload.size)), StandardCharsets.UTF_8)
    } catch (_: Exception) {
        null
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).run {
            init(
                KeyGenParameterSpec.Builder(
                    alias,
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
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_IV_LENGTH = 12
        const val GCM_TAG_LENGTH = 128
    }
}
