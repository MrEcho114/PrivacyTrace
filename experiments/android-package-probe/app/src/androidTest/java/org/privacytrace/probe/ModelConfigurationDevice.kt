package org.privacytrace.probe

import android.content.Context
import android.util.AtomicFile
import java.security.KeyStore

private const val DEVICE_ENDPOINT = "https://synthetic.example.test/v1"
private const val DEVICE_SECRET = "synthetic-device-only-key"

private fun unavailable(action: () -> Unit) {
    try { action(); error("Expected fixed refusal") } catch (error: ModelConfigException) {
        check(error.code == "MODEL_CONFIG_UNAVAILABLE")
        check(error.cause == null && error.message == error.code)
    }
}

internal fun verifyModelStore(context: Context) {
    val files = AndroidModelConfigFiles(context)
    val keys = AndroidModelConfigKeys()
    val store = androidModelConfiguration(context)
    store.clear()
    try {
        val input = DEVICE_SECRET.toCharArray()
        val prepared = store.prepareSave(DEVICE_ENDPOINT, input)
        check(input.all { it == '\u0000' } && files.read() == null)
        store.commitSave(prepared)
        check(keys.key(false).encoded == null)
        check(!String(checkNotNull(files.read()), Charsets.ISO_8859_1).contains(DEVICE_SECRET))
        check(androidModelConfiguration(context).status().endpoint == DEVICE_ENDPOINT)
        store.withSecret(DEVICE_ENDPOINT) { check(String(it, Charsets.US_ASCII) == DEVICE_SECRET) }
        try {
            store.withSecret("https://other.example.test/v1") { error("Key must not cross endpoint") }
            error("Expected endpoint refusal")
        } catch (error: ModelConfigException) { check(error.code == "MODEL_ENDPOINT_MISMATCH") }

        // Intentional test-only incomplete write, simulating death before finishWrite.
        AtomicFile(files.file).startWrite().apply { write(byteArrayOf(1, 2, 3)); close() }
        check(androidModelConfiguration(context).status().endpoint == DEVICE_ENDPOINT)

        val record = checkNotNull(files.read())
        record[record.lastIndex] = (record.last().toInt() xor 1).toByte()
        files.write(record)
        unavailable { store.status() }
        store.clear()
        store.commitSave(store.prepareSave(DEVICE_ENDPOINT, DEVICE_SECRET.toCharArray()))
        keys.delete()
        unavailable { androidModelConfiguration(context).status() }
        check(!KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.containsAlias(AndroidModelConfigKeys.ALIAS))
        store.clear()
        check(androidModelConfiguration(context).status().endpoint == null && files.read() == null)
    } finally { store.clear() }
}

internal fun seedModelStore(context: Context) {
    val store = androidModelConfiguration(context)
    store.clear()
    store.commitSave(store.prepareSave(DEVICE_ENDPOINT, DEVICE_SECRET.toCharArray()))
}

internal fun verifyReopenedModelStore(context: Context) {
    val store = androidModelConfiguration(context)
    try {
        check(store.status().endpoint == DEVICE_ENDPOINT)
        store.withSecret(DEVICE_ENDPOINT) { check(String(it, Charsets.US_ASCII) == DEVICE_SECRET) }
    } finally { store.clear() }
}
