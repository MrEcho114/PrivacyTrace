package org.privacytrace.probe

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.URI
import java.util.Locale
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal class ModelConfigException(val code: String) : Exception(code)
internal data class ModelConfigStatus(val endpoint: String?)
internal class PreparedModelConfig(val endpoint: String, internal val record: ByteArray)

internal interface ModelConfigFiles {
    fun read(): ByteArray?
    fun write(record: ByteArray)
    fun delete()
}

internal interface ModelConfigKeys {
    fun key(create: Boolean): SecretKey
    fun delete()
}

// Only native callers can use this module. No command exports decrypted bytes.
internal class ModelConfiguration(private val files: ModelConfigFiles, private val keys: ModelConfigKeys) {
    companion object {
        const val MAX_RECORD = 8192
        const val MAX_KEY = 4096
        const val MAX_ENDPOINT = 1024
        private const val VERSION = 1
        // Shared across Activity recreation, including workers still draining old requests.
        private val MUTEX = Any()

        fun endpoint(value: String): String = try {
            require(value.length in 1..MAX_ENDPOINT && value.all { it.code in 33..126 })
            val uri = URI(value)
            require(uri.scheme.equals("https", ignoreCase = true) && uri.host != null)
            require(uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null)
            require(uri.port == -1 || uri.port in 1..65535)
            require(uri.normalize() == uri)
            val port = if (uri.port == -1 || uri.port == 443) "" else ":${uri.port}"
            "https://${uri.host.lowercase(Locale.ROOT)}$port${uri.rawPath.orEmpty().ifEmpty { "/" }}"
        } catch (_: Exception) {
            throw ModelConfigException("INVALID_MODEL_CONFIG")
        }
    }

    // Encrypt on a worker; the caller must publish only its still-active operation.
    // Ownership of the input array is consumed even on failure.
    fun prepareSave(address: String, secret: CharArray, cancelled: () -> Boolean = { false }): PreparedModelConfig = synchronized(MUTEX) {
        var bytes: ByteArray? = null
        try {
            if (cancelled()) throw ModelConfigException("CANCELLED")
            val target = endpoint(address)
            if (secret.size !in 1..MAX_KEY || secret.any { it.code !in 33..126 }) {
                throw ModelConfigException("INVALID_MODEL_CONFIG")
            }
            val plain = ByteArray(secret.size) { secret[it].code.toByte() }
            bytes = plain
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, keys.key(create = true))
            cipher.updateAAD(aad(target))
            val encrypted = cipher.doFinal(plain)
            val iv = cipher.iv
            check(iv.size == 12)
            val output = ByteArrayOutputStream()
            DataOutputStream(output).use {
                it.writeInt(VERSION)
                it.writeUTF(target)
                it.write(iv)
                it.writeInt(encrypted.size)
                it.write(encrypted)
            }
            val record = output.toByteArray()
            check(record.size <= MAX_RECORD)
            PreparedModelConfig(target, record)
        } catch (error: ModelConfigException) {
            throw error
        } catch (_: Exception) {
            throw ModelConfigException("MODEL_CONFIG_UNAVAILABLE")
        } finally {
            secret.fill('\u0000')
            bytes?.fill(0)
        }
    }

    // Small atomic-file commit runs on the UI queue after checking the operation token.
    // Pause/cancel cannot interleave between the token check, commit and Invoke completion.
    fun commitSave(prepared: PreparedModelConfig): ModelConfigStatus = guarded {
        files.write(prepared.record)
        ModelConfigStatus(prepared.endpoint)
    }

    fun status(): ModelConfigStatus = guarded {
        val record = files.read() ?: return@guarded ModelConfigStatus(null)
        decrypt(record) { target, _ -> ModelConfigStatus(target) }
    }

    fun <T> withSecret(address: String, action: (ByteArray) -> T): T {
        val target = endpoint(address)
        return guarded {
            val record = files.read() ?: throw ModelConfigException("MODEL_CONFIG_UNAVAILABLE")
            decrypt(record) { stored, bytes ->
                if (stored != target) throw ModelConfigException("MODEL_ENDPOINT_MISMATCH")
                action(bytes)
            }
        }
    }

    fun clear(): ModelConfigStatus = guarded {
        // Revoke the wrapping key first; leftover ciphertext then fails closed.
        keys.delete()
        files.delete()
        ModelConfigStatus(null)
    }

    private fun <T> decrypt(record: ByteArray, action: (String, ByteArray) -> T): T {
        check(record.size <= MAX_RECORD)
        val input = DataInputStream(ByteArrayInputStream(record))
        check(input.readInt() == VERSION)
        val target = input.readUTF()
        check(endpoint(target) == target)
        val iv = ByteArray(12).also { input.readFully(it) }
        val size = input.readInt()
        check(size in 17..(MAX_KEY + 16))
        val encrypted = ByteArray(size).also { input.readFully(it) }
        check(input.read() == -1)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        // Reading must never create a replacement key for an existing ciphertext.
        cipher.init(Cipher.DECRYPT_MODE, keys.key(create = false), GCMParameterSpec(128, iv))
        cipher.updateAAD(aad(target))
        val plain = cipher.doFinal(encrypted)
        try {
            check(plain.size in 1..MAX_KEY && plain.all { it.toInt() in 33..126 })
            return action(target, plain)
        } finally {
            plain.fill(0)
        }
    }

    private fun aad(target: String) = "privacytrace:model-config:v1:$target".toByteArray(Charsets.UTF_8)

    private inline fun <T> guarded(action: () -> T): T = synchronized(MUTEX) {
        try {
            action()
        } catch (error: ModelConfigException) {
            throw error
        } catch (_: Exception) {
            throw ModelConfigException("MODEL_CONFIG_UNAVAILABLE")
        }
    }
}
