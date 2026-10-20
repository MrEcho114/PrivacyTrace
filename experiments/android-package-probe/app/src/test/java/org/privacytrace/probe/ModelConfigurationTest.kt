package org.privacytrace.probe

import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import org.junit.Assert.*
import org.junit.Test

class ModelConfigurationTest {
    private val address = "https://model.example.test/v1"
    private class Files : ModelConfigFiles {
        var bytes: ByteArray? = null
        var refuseWrite = false
        override fun read() = bytes?.clone()
        override fun write(record: ByteArray) {
            check(!refuseWrite)
            bytes = record.clone()
        }
        override fun delete() { bytes = null }
    }
    private class Keys : ModelConfigKeys {
        var value: SecretKey? = null
        var created = 0
        override fun key(create: Boolean): SecretKey {
            if (value == null && create) {
                value = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
                created++
            }
            return checkNotNull(value)
        }
        override fun delete() { value = null }
    }

    private fun expect(code: String, action: () -> Unit) {
        try { action(); fail("Expected fixed failure") } catch (error: ModelConfigException) {
            assertEquals(code, error.code)
            assertEquals(code, error.message)
            assertNull(error.cause)
        }
    }

    @Test fun `save encrypts and reopen authenticates without exposing key in status`() {
        val files = Files()
        val keys = Keys()
        val store = ModelConfiguration(files, keys)
        val secret = "synthetic-local-key".toCharArray()
        val prepared = store.prepareSave(address, secret)
        assertTrue(secret.all { it == '\u0000' })
        assertNull(files.bytes)
        store.commitSave(prepared)
        assertFalse(String(files.bytes!!, Charsets.ISO_8859_1).contains("synthetic-local-key"))
        val reopened = ModelConfiguration(files, keys)
        assertEquals(address, reopened.status().endpoint)
        assertFalse(reopened.status().toString().contains("synthetic-local-key"))
        reopened.withSecret(address) { assertEquals("synthetic-local-key", String(it, Charsets.US_ASCII)) }
        assertEquals(1, keys.created)
    }

    @Test fun `endpoint canonicalization retains path and nondefault port identity`() {
        assertEquals("https://model.example.test/", ModelConfiguration.endpoint("HTTPS://MODEL.EXAMPLE.TEST:443"))
        assertEquals("https://model.example.test:8443/v1/", ModelConfiguration.endpoint("https://model.example.test:8443/v1/"))
    }

    @Test fun `other origin port or path never receives the stored secret`() {
        val store = ModelConfiguration(Files(), Keys())
        store.commitSave(store.prepareSave(address, "synthetic-key".toCharArray()))
        listOf("https://other.example.test/v1", "https://model.example.test:8443/v1", "$address/", "https://model.example.test/v2").forEach {
            expect("MODEL_ENDPOINT_MISMATCH") { store.withSecret(it) { fail("Must not deliver a key") } }
        }
    }

    @Test fun `unsafe endpoints and invalid keys fail without storing and wipe input`() {
        val files = Files()
        val keys = Keys()
        val store = ModelConfiguration(files, keys)
        listOf("http://model.example.test", "https://user:password@model.example.test", "$address?key=x", "$address#fragment", "https://model.example.test/a/../v1", " https://model.example.test", "https://model.example.test:0").forEach {
            val secret = "synthetic-key".toCharArray()
            expect("INVALID_MODEL_CONFIG") { store.prepareSave(it, secret) }
            assertTrue(secret.all { ch -> ch == '\u0000' })
        }
        listOf("", "contains space", "contains\nnewline", "x".repeat(4097)).forEach {
            val secret = it.toCharArray()
            expect("INVALID_MODEL_CONFIG") { store.prepareSave(address, secret) }
            assertTrue(secret.all { ch -> ch == '\u0000' })
        }
        assertNull(files.bytes)
        assertEquals(0, keys.created)
    }

    @Test fun `fresh IV makes equal saves different and tampering fails closed`() {
        val files = Files()
        val keys = Keys()
        val store = ModelConfiguration(files, keys)
        val first = store.prepareSave(address, "synthetic-key".toCharArray())
        val second = store.prepareSave(address, "synthetic-key".toCharArray())
        assertFalse(first.record.contentEquals(second.record))
        store.commitSave(first)
        files.bytes!![files.bytes!!.lastIndex] = (files.bytes!!.last().toInt() xor 1).toByte()
        expect("MODEL_CONFIG_UNAVAILABLE") { store.status() }
        assertEquals(1, keys.created)
    }

    @Test fun `ciphertext transplanted under another valid endpoint is rejected by AAD`() {
        val files = Files()
        val store = ModelConfiguration(files, Keys())
        store.commitSave(store.prepareSave(address, "synthetic-key".toCharArray()))
        val original = files.bytes!!
        val index = String(original, Charsets.ISO_8859_1).indexOf("model.example.test")
        assertTrue(index >= 0)
        original[index] = 'n'.code.toByte()
        expect("MODEL_CONFIG_UNAVAILABLE") { store.status() }
    }

    @Test fun `lost wrapping key never silently creates a new key during read`() {
        val files = Files()
        val keys = Keys()
        val store = ModelConfiguration(files, keys)
        store.commitSave(store.prepareSave(address, "synthetic-key".toCharArray()))
        keys.delete()
        expect("MODEL_CONFIG_UNAVAILABLE") { ModelConfiguration(files, keys).status() }
        assertEquals(1, keys.created)
        store.clear()
        assertNull(store.status().endpoint)
        store.commitSave(store.prepareSave(address, "replacement-synthetic-key".toCharArray()))
        assertEquals(address, store.status().endpoint)
    }

    @Test fun `clear removes stored data and key then reopen stays unconfigured`() {
        val files = Files()
        val keys = Keys()
        val store = ModelConfiguration(files, keys)
        store.commitSave(store.prepareSave(address, "synthetic-key".toCharArray()))
        store.clear()
        assertNull(ModelConfiguration(files, keys).status().endpoint)
        assertNull(keys.value)
        assertNull(files.bytes)
    }

    @Test fun `unpublished or failed replacement does not replace current configuration`() {
        val files = Files()
        val store = ModelConfiguration(files, Keys())
        store.commitSave(store.prepareSave(address, "original-synthetic-key".toCharArray()))
        val prepared = store.prepareSave("https://other.example.test/v2", "new-synthetic-key".toCharArray())
        assertEquals(address, store.status().endpoint)
        files.refuseWrite = true
        expect("MODEL_CONFIG_UNAVAILABLE") { store.commitSave(prepared) }
        assertEquals(address, store.status().endpoint)
        store.withSecret(address) { assertEquals("original-synthetic-key", String(it, Charsets.US_ASCII)) }
    }

    @Test fun `decrypted buffer is wiped even when native consumer fails`() {
        val store = ModelConfiguration(Files(), Keys())
        store.commitSave(store.prepareSave(address, "synthetic-key".toCharArray()))
        var buffer: ByteArray? = null
        expect("MODEL_CONFIG_UNAVAILABLE") {
            store.withSecret(address) { buffer = it; error("Do not leak synthetic diagnostics") }
        }
        assertTrue(buffer!!.all { it == 0.toByte() })
    }

    @Test fun `oversized truncated and trailing records never become configured`() {
        val files = Files()
        val store = ModelConfiguration(files, Keys())
        val valid = store.prepareSave(address, "synthetic-key".toCharArray()).record
        listOf(ByteArray(8193), valid.copyOf(8), valid + byteArrayOf(1)).forEach {
            files.bytes = it
            expect("MODEL_CONFIG_UNAVAILABLE") { store.status() }
        }
    }

    @Test fun `cancelled preparation consumes input without creating a key or file`() {
        val files = Files()
        val keys = Keys()
        val input = "synthetic-key".toCharArray()
        expect("CANCELLED") { ModelConfiguration(files, keys).prepareSave(address, input) { true } }
        assertTrue(input.all { it == '\u0000' })
        assertNull(files.bytes)
        assertEquals(0, keys.created)
    }

    @Test fun `new instance clear waits for old worker and leaves no resurrected alias`() {
        val files = Files()
        val keys = Keys()
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(2)
        val blocking = object : ModelConfigKeys by keys {
            override fun key(create: Boolean): SecretKey {
                entered.countDown()
                check(release.await(5, TimeUnit.SECONDS))
                return keys.key(create)
            }
        }
        try {
            val old = pool.submit<PreparedModelConfig> {
                ModelConfiguration(files, blocking).prepareSave(address, "synthetic-key".toCharArray())
            }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val cleared = CountDownLatch(1)
            val clear = pool.submit {
                ModelConfiguration(files, keys).clear()
                cleared.countDown()
            }
            assertFalse(cleared.await(100, TimeUnit.MILLISECONDS))
            release.countDown()
            old.get(5, TimeUnit.SECONDS) // Stale prepared record is never published by its cancelled caller.
            clear.get(5, TimeUnit.SECONDS)
            assertNull(keys.value)
            assertNull(files.bytes)
            assertNull(ModelConfiguration(files, keys).status().endpoint)
        } finally { release.countDown(); pool.shutdownNow() }
    }

    @Test fun `preparation cancelled while waiting for another instance never recreates a key`() {
        val files = Files()
        val keys = Keys()
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val waiting = CountDownLatch(1)
        val cancelled = AtomicBoolean(false)
        val input = "synthetic-pending-key".toCharArray()
        val pool = Executors.newFixedThreadPool(2)
        val blocking = object : ModelConfigKeys by keys {
            override fun key(create: Boolean): SecretKey {
                entered.countDown()
                check(release.await(5, TimeUnit.SECONDS))
                return keys.key(create)
            }
        }
        try {
            val old = pool.submit<PreparedModelConfig> {
                ModelConfiguration(files, blocking).prepareSave(address, "synthetic-key".toCharArray())
            }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val pending = pool.submit {
                waiting.countDown()
                expect("CANCELLED") { ModelConfiguration(files, keys).prepareSave(address, input) { cancelled.get() } }
            }
            assertTrue(waiting.await(5, TimeUnit.SECONDS))
            cancelled.set(true)
            release.countDown()
            old.get(5, TimeUnit.SECONDS)
            pending.get(5, TimeUnit.SECONDS)
            assertTrue(input.all { it == '\u0000' })
            assertEquals(1, keys.created)
            assertNull(files.bytes)
        } finally { release.countDown(); pool.shutdownNow() }
    }
}
