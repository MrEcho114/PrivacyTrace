package org.privacytrace.probe

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

internal class AndroidModelConfigFiles(context: Context, name: String = "model-config-v1.bin") : ModelConfigFiles {
    internal val file = File(context.noBackupFilesDir, name)
    private val atomic = AtomicFile(file)

    override fun read(): ByteArray? {
        if (!file.exists() && !File(file.path + ".bak").exists()) return null
        return atomic.openRead().use { stream ->
            val bytes = ByteArray(ModelConfiguration.MAX_RECORD + 1)
            var count = 0
            while (count < bytes.size) {
                val read = stream.read(bytes, count, bytes.size - count)
                if (read < 0) break
                count += read
            }
            check(count <= ModelConfiguration.MAX_RECORD)
            bytes.copyOf(count)
        }
    }

    override fun write(record: ByteArray) {
        check(record.size <= ModelConfiguration.MAX_RECORD)
        val stream = atomic.startWrite()
        try {
            stream.write(record)
            atomic.finishWrite(stream)
            // AtomicFile may log a failed rename/sync instead of throwing.
            check(read()?.contentEquals(record) == true)
        } catch (error: Exception) {
            atomic.failWrite(stream)
            throw error
        }
    }

    override fun delete() {
        atomic.delete()
        check(listOf(file, File(file.path + ".bak"), File(file.path + ".new")).none { it.exists() })
    }
}

internal class AndroidModelConfigKeys(private val alias: String = ALIAS) : ModelConfigKeys {
    companion object { internal const val ALIAS = "privacytrace.model-config.v1" }
    private fun store() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    override fun key(create: Boolean): SecretKey {
        val keyStore = store()
        if (keyStore.containsAlias(alias)) return keyStore.getKey(alias, null) as SecretKey
        check(create)
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true)
                .build())
        }.generateKey()
    }

    override fun delete() { store().deleteEntry(alias) }
}

internal fun androidModelConfiguration(context: Context) =
    ModelConfiguration(AndroidModelConfigFiles(context.applicationContext), AndroidModelConfigKeys())
