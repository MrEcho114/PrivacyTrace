package org.privacytrace.probe

import java.io.File
import java.util.concurrent.TimeUnit
import java.util.zip.ZipInputStream
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.SocketPolicy
import org.junit.Assert.*
import org.junit.Test

class AnalysisTransportTest {
    companion object {
        internal var cacheRoot: File? = null
    }
    private fun temporaryDirectory(): File = File.createTempFile("pt-upload-test", ".tmp", cacheRoot).apply {
        check(delete()); check(mkdir())
    }
    private val instance = "12345678-1234-4234-8234-123456789abc"
    private val draft = "a".repeat(32)
    private val token = "pt_cap_" + "synthetic".repeat(4)
    private val caps = UploadCapabilities(instance, 157286400, 157286400, 157286400, 101)
    private fun capabilities(id: String = instance) = """{"protocol":"privacytrace-mobile/1","supported":true,"instance_id":"$id","upload_format":"apk-or-zip","max_upload_bytes":157286400,"max_file_bytes":157286400,"max_total_bytes":157286400,"max_files":101,"retention":"UNTIL_EXPLICIT_DELETE","delete_draft":true}"""
    private class Sessions : UploadSessions {
        var value: UploadSession? = null
        override fun load(origin: String, instance: String): UploadSession? {
            val saved = value ?: return null
            if (saved.origin != origin) return null
            if (saved.instance != instance) throw ServerProbeException("INSTANCE_MISMATCH")
            return saved
        }
        override fun save(session: UploadSession, cancelled: () -> Boolean) {
            if (cancelled()) throw ServerProbeException("CANCELLED")
            value = session
        }
        override fun clear(origin: String, instance: String) { load(origin, instance); value = null }
    }
    private class Source : PackageSource {
        val bytes = listOf("synthetic base bytes".toByteArray(), "synthetic split bytes".toByteArray())
        val installed = Installation("org.example.synthetic", 123, 44,
            listOf(InstalledPart(null, "base", bytes[0].size.toLong(), 1),
                InstalledPart("feature", "split", bytes[1].size.toLong(), 1)))
        override fun snapshot(packageName: String) = installed
        override fun open(part: InstalledPart) = bytes[if (part.splitName == null) 0 else 1].inputStream()
    }
    private fun receipt(result: ProbeResult, wrong: Boolean = false): String {
        val parts = result.parts.mapIndexed { index, part ->
            """{"package_name":"${result.packageName}","version_code":123,"part":"${if (index == 0) "BASE" else "SPLIT"}","split_name":${part.splitName?.let { "\"$it\"" } ?: "null"},"size_bytes":${part.bytes},"sha256":"${if (wrong) "f".repeat(64) else part.sha256}"}"""
        }
        return """{"id":"$draft","uploaded":true,"package_set":{"package_name":"${result.packageName}","version_code":123,"base":${parts[0]},"splits":[${parts[1]}],"total_size_bytes":${result.totalBytes}}}"""
    }
    private fun expect(code: String, action: () -> Unit) {
        try { action(); fail("expected $code") } catch (error: ServerProbeException) {
            assertEquals(code, error.code)
        }
    }
    private fun archive(action: (UploadArchive, Source, File) -> Unit) {
        val root = temporaryDirectory()
        val source = Source()
        try {
            UploadArchive.prepare(root, source, source.installed, caps) { false }.use { action(it, source, root) }
            assertEquals(0, root.listFiles()!!.size)
        } finally { root.deleteRecursively() }
    }
    @Test fun archiveContainsAllPartsAndCleans() = archive { archive, source, _ ->
        assertEquals(archive.result.localSetSha256,
            receiptFingerprint(archive.result.packageName, 123, archive.result.parts))
        ZipInputStream(archive.file.inputStream()).use { zip ->
            assertEquals("base.apk", zip.nextEntry.name); assertArrayEquals(source.bytes[0], zip.readBytes())
            assertEquals("part-1.apk", zip.nextEntry.name); assertArrayEquals(source.bytes[1], zip.readBytes())
            assertNull(zip.nextEntry)
        }
    }
    @Test fun singleApkUsesRawBodyAtWireLimit() {
        val root = temporaryDirectory()
        val source = Source()
        val single = object : PackageSource {
            override fun snapshot(packageName: String) = source.installed.copy(parts=source.installed.parts.take(1))
            override fun open(part: InstalledPart) = source.open(part)
        }
        try {
            val confirmed = single.snapshot(source.installed.packageName)
            UploadArchive.prepare(root, single, confirmed, caps.copy(maxUpload=source.bytes[0].size.toLong())) { false }.use {
                assertArrayEquals(source.bytes[0], it.file.readBytes())
            }
            assertEquals(0, root.listFiles()!!.size)
        } finally { root.deleteRecursively() }
    }
    @Test fun failuresLeaveNoTemporaryApks() {
        val root = temporaryDirectory()
        val source = Source()
        try {
            try {
                UploadArchive.prepare(root, source, source.installed.copy(updatedMillis=45), caps) { false }
                fail("changed installation")
            } catch (error: ProbeException) { assertEquals(ProbeFailure.INSTALLATION_CHANGED, error.failure) }
            try {
                // Raw files fit; the ZIP wrapper itself must still be bounded.
                UploadArchive.prepare(root, source, source.installed,
                    caps.copy(maxUpload=source.bytes.sumOf { it.size }.toLong())) { false }
                fail("limit")
            } catch (error: ProbeException) { assertEquals(ProbeFailure.LIMIT_EXCEEDED, error.failure) }
            try {
                UploadArchive.prepare(root, source, source.installed, caps) { true }
                fail("cancel")
            } catch (error: ProbeException) { assertEquals(ProbeFailure.CANCELLED, error.failure) }
            assertEquals(0, root.listFiles()!!.size)
        } finally { root.deleteRecursively() }
    }
    @Test fun tlsUploadChecksReceiptAndReadback() = archive { archive, _, _ ->
        HealthTlsFixture().use { f ->
            val sessions = Sessions()
            f.server.enqueue(f.json(capabilities()))
            f.server.enqueue(f.json("""{"id":"$draft","capability_token":"$token"}"""))
            f.server.enqueue(f.json(receipt(archive.result)))
            f.server.enqueue(f.json(receipt(archive.result)))
            val stages = mutableListOf<String>()
            val transport = AnalysisTransport(f.origin, sessions, f.client) { stages.add(it) }
            assertEquals("SERVER_CONFIRMED", transport.upload(archive, caps).state)
            assertEquals(listOf("CHECKING_INSTANCE", "CREATING_DRAFT", "PROTECTING_ACCESS", "UPLOADING", "CONFIRMING"), stages)
            val requests = (1..4).map { checkNotNull(f.server.takeRequest(2, TimeUnit.SECONDS)) }
            assertEquals(listOf("GET", "POST", "POST", "GET"), requests.map { it.method })
            assertNull(requests[0].getHeader("Authorization")); assertNull(requests[1].getHeader("Authorization"))
            assertEquals("Bearer $token", requests[2].getHeader("Authorization"))
            assertEquals("/api/v1/web/drafts/$draft/package-set", requests[2].path)
            assertArrayEquals(archive.file.readBytes(), requests[2].body.readByteArray())
            assertTrue(requests.none { it.path!!.contains(token) || it.getHeader("Cookie") != null })
            assertNotNull(sessions.value)
        }
    }
    @Test fun mismatchedReceiptRetainsAccess() = archive { archive, _, _ ->
        HealthTlsFixture().use { f ->
            val sessions = Sessions()
            f.server.enqueue(f.json(capabilities()))
            f.server.enqueue(f.json("""{"id":"$draft","capability_token":"$token"}"""))
            f.server.enqueue(f.json(receipt(archive.result, true)))
            expect("UPLOAD_RECEIPT_MISMATCH") { AnalysisTransport(f.origin, sessions, f.client).upload(archive, caps) }
            assertNotNull(sessions.value); assertEquals(3, f.server.requestCount)
        }
    }
    @Test fun lostResponseReconcilesWithoutReplay() = archive { archive, _, _ ->
        HealthTlsFixture().use { f ->
            val sessions = Sessions()
            f.server.enqueue(f.json(capabilities()))
            f.server.enqueue(f.json("""{"id":"$draft","capability_token":"$token"}"""))
            f.server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
            expect("SERVER_UNREACHABLE") { AnalysisTransport(f.origin, sessions, f.client).upload(archive, caps) }
            assertNotNull(sessions.value)
            f.server.enqueue(f.json(capabilities())); f.server.enqueue(f.json(receipt(archive.result)))
            assertEquals("SERVER_CONFIRMED", AnalysisTransport(f.origin, sessions, f.client).refresh().state)
            assertEquals(5, f.server.requestCount)
            val requests = (1..5).map { checkNotNull(f.server.takeRequest(2, TimeUnit.SECONDS)) }
            assertEquals(1, requests.count { it.path!!.endsWith("package-set") })
        }
    }
    @Test fun instanceReplacementRefusesCredentials() {
        HealthTlsFixture().use { f ->
            val sessions = Sessions().apply { value = UploadSession(f.origin, instance, draft, token, "f".repeat(64)) }
            f.server.enqueue(f.json(capabilities("22345678-1234-4234-8234-123456789abc")))
            expect("INSTANCE_MISMATCH") { AnalysisTransport(f.origin, sessions, f.client).refresh() }
            assertEquals(1, f.server.requestCount)
            assertNull(f.server.takeRequest(2, TimeUnit.SECONDS)!!.getHeader("Authorization"))
        }
    }
    @Test fun otherOriginReceivesNoCredentials() {
        HealthTlsFixture().use { first -> HealthTlsFixture().use { other ->
            val sessions = Sessions().apply { value = UploadSession(first.origin, instance, draft, token, "f".repeat(64)) }
            other.server.enqueue(other.json(capabilities()))
            expect("NO_SAVED_UPLOAD") { AnalysisTransport(other.origin, sessions, other.client).refresh() }
            assertEquals(1, other.server.requestCount); assertEquals(0, first.server.requestCount)
            assertNull(other.server.takeRequest(2, TimeUnit.SECONDS)!!.getHeader("Authorization"))
        } }
    }
    @Test fun redirectAndBackpressureNeverReplay() {
        HealthTlsFixture().use { f -> HealthTlsFixture().use { other ->
            for ((code, expected) in listOf(302 to "SERVER_REDIRECT_REJECTED", 429 to "SERVER_BUSY", 503 to "SERVER_BUSY")) {
                f.server.enqueue(f.json().setResponseCode(code).setHeader("Location", other.origin).setHeader("Retry-After", "0"))
                expect(expected) { AnalysisTransport(f.origin, Sessions(), f.client).capabilities() }
            }
            assertEquals(3, f.server.requestCount); assertEquals(0, other.server.requestCount)
        } }
    }
    @Test fun deleteWaitsForServerAcknowledgement() {
        HealthTlsFixture().use { f ->
            val sessions = Sessions().apply { value = UploadSession(f.origin, instance, draft, token, "f".repeat(64)) }
            f.server.enqueue(f.json(capabilities())); f.server.enqueue(f.json().setResponseCode(503))
            expect("SERVER_BUSY") { AnalysisTransport(f.origin, sessions, f.client).delete() }
            assertNotNull(sessions.value)
            f.server.enqueue(f.json(capabilities())); f.server.enqueue(f.json("""{"deleted":true,"cleanup_pending":true}"""))
            val status = AnalysisTransport(f.origin, sessions, f.client).delete()
            assertEquals("DELETED", status.state); assertTrue(status.cleanupPending); assertNull(sessions.value)
        }
    }
    @Test fun strictJsonRejectsAmbiguity() {
        for (json in listOf("{\"a\":1,\"a\":2}", "{\"a\":01}", "{\"a\":1.2}", "{\"a\":1}{}", "{\"a\":\"\\q\"}")) {
            expect("SERVER_RESPONSE_INVALID") { TransportJson.decode(json.toByteArray()) }
        }
        HealthTlsFixture().use { f ->
            for (json in listOf("{}", capabilities().replace("true", "false"), capabilities().replace("UNTIL_EXPLICIT_DELETE", "24H"))) {
                f.server.enqueue(f.json(json))
                expect("SERVER_INCOMPATIBLE") { AnalysisTransport(f.origin, Sessions(), f.client).capabilities() }
            }
        }
    }
    @Test fun cancelBeforeSendEmitsNoRequests() {
        HealthTlsFixture().use { f ->
            val transport = AnalysisTransport(f.origin, Sessions(), f.client)
            transport.cancel()
            expect("CANCELLED") { transport.refresh() }
            assertEquals(0, f.server.requestCount)
        }
    }
    @Test fun cancelInFlightStopsSocket() {
        HealthTlsFixture().use { f ->
            f.server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val transport = AnalysisTransport(f.origin, Sessions(), f.client)
            val worker = java.util.concurrent.Executors.newSingleThreadExecutor()
            try {
                val done = worker.submit<String> {
                    try { transport.refresh(); "unexpected success" }
                    catch (error: ServerProbeException) { error.code }
                }
                assertNotNull(f.server.takeRequest(3, TimeUnit.SECONDS))
                transport.cancel()
                assertEquals("CANCELLED", done.get(3, TimeUnit.SECONDS))
                assertEquals(1, f.server.requestCount)
            } finally { worker.shutdownNow() }
        }
    }
}
