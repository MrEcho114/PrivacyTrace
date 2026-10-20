package org.privacytrace.probe

import java.io.ByteArrayOutputStream
import java.io.File
import java.io.InterruptedIOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import javax.net.ssl.SSLException
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

internal data class UploadSession(
    val origin: String, val instance: String, val draft: String, val token: String,
    val fingerprint: String,
)
internal interface UploadSessions {
    fun load(origin: String, instance: String): UploadSession?
    fun save(session: UploadSession, cancelled: () -> Boolean = { false })
    fun clear(origin: String, instance: String)
}
internal data class UploadStatus(val origin: String, val draft: String, val state: String,
    val cleanupPending: Boolean = false)

// No arbitrary request API, no web-supplied headers, no model configuration.
internal class AnalysisTransport(address: String, private val sessions: UploadSessions,
    client: OkHttpClient = healthHttpClient()) {
    val origin = analysisOrigin(address)
    private val cancelled = AtomicBoolean(false)
    private val current = AtomicReference<Call?>()
    private val dns = HealthDns(client.dns)
    private val http = client.newBuilder().dns(dns)
        .writeTimeout(30, TimeUnit.SECONDS).readTimeout(180, TimeUnit.SECONDS)
        .callTimeout(240, TimeUnit.SECONDS).build()

    fun cancel() { cancelled.set(true); dns.cancel(); current.get()?.cancel() }
    fun checkCancelled() { if (cancelled.get()) throw ServerProbeException("CANCELLED") }

    private fun exchange(path: String, method: String = "GET", session: UploadSession? = null,
                         json: String? = null, file: File? = null): Map<String, Any?> {
        checkCancelled()
        if (session != null && session.origin != origin) throw ServerProbeException("INSTANCE_MISMATCH")
        val body = if (file != null) file.asRequestBody("application/octet-stream".toMediaType())
            else json?.toRequestBody("application/json".toMediaType())
        val request = Request.Builder().url(origin + path).method(method, body)
            .header("Accept", "application/json").header("Cache-Control", "no-store")
            .header("User-Agent", "PrivacyTrace-Android")
        if (session != null) request.header("Authorization", "Bearer ${session.token}")
        val call = http.newCall(request.build())
        current.set(call)
        if (cancelled.get()) call.cancel()
        try {
            return call.execute().use { response ->
                checkCancelled()
                when {
                    response.code in 300..399 -> throw ServerProbeException("SERVER_REDIRECT_REJECTED")
                    response.code == 413 -> throw ServerProbeException("LIMIT_EXCEEDED")
                    response.code in setOf(401, 403) -> throw ServerProbeException("ACCESS_REJECTED")
                    response.code == 409 -> throw ServerProbeException("UPLOAD_CONFLICT_REFRESH")
                    response.code !in 200..299 -> throw ServerProbeException("SERVER_REJECTED")
                }
                val content = response.body ?: throw ServerProbeException("SERVER_RESPONSE_INVALID")
                val type = content.contentType()
                if (type?.type != "application" || type.subtype != "json") throw ServerProbeException("SERVER_RESPONSE_INVALID")
                val max = 512 * 1024
                if (content.contentLength() > max) throw ServerProbeException("SERVER_RESPONSE_TOO_LARGE")
                val output = ByteArrayOutputStream()
                content.byteStream().use { input ->
                    val buffer = ByteArray(8192)
                    while (true) {
                        checkCancelled()
                        val count = input.read(buffer, 0, minOf(buffer.size, max + 1 - output.size()))
                        if (count < 0) break
                        output.write(buffer, 0, count)
                        if (output.size() > max) throw ServerProbeException("SERVER_RESPONSE_TOO_LARGE")
                    }
                }
                TransportJson.decode(output.toByteArray())
            }
        } catch (error: ServerProbeException) { throw error }
        catch (_: SSLException) { throw ServerProbeException(if (cancelled.get()) "CANCELLED" else "SERVER_TLS_REJECTED") }
        catch (_: InterruptedIOException) { throw ServerProbeException(if (cancelled.get()) "CANCELLED" else "SERVER_TIMEOUT") }
        catch (_: Exception) { throw ServerProbeException(if (cancelled.get()) "CANCELLED" else "SERVER_UNREACHABLE") }
        finally { current.compareAndSet(call, null) }
    }

    fun capabilities(): UploadCapabilities {
        val fields = exchange("api/v1/mobile-capabilities")
        try {
            check(fields["protocol"] == "privacytrace-mobile/1" && fields["supported"] == true)
            check(fields["upload_format"] == "apk-or-zip" && fields["retention"] == "UNTIL_EXPLICIT_DELETE")
            check(fields["delete_draft"] == true)
            val instance = fields.text("instance_id")
            check(UUID.fromString(instance).toString() == instance)
            val upload = fields.number("max_upload_bytes")
            val file = fields.number("max_file_bytes")
            val total = fields.number("max_total_bytes")
            val count = fields.number("max_files")
            check(upload in 1..(1024L * 1024 * 1024) && file in 1..(1024L * 1024 * 1024) &&
                total in 1..(1024L * 1024 * 1024) && count in 1..101)
            return UploadCapabilities(instance, upload, file, total, count.toInt())
        } catch (_: Exception) { throw ServerProbeException("SERVER_INCOMPATIBLE") }
    }

    fun upload(archive: UploadArchive, consent: UploadCapabilities): UploadStatus {
        // A fresh negotiation immediately before credentials/bytes are sent must
        // match the instance and limits the user actually confirmed.
        if (capabilities() != consent) throw ServerProbeException("INSTANCE_MISMATCH")
        var session = sessions.load(origin, consent.instanceId)
        if (session != null) {
            if (session.fingerprint != archive.result.localSetSha256) throw ServerProbeException("EXISTING_UPLOAD_DELETE_FIRST")
            val existing = get(session)
            if (existing.state == "SERVER_CONFIRMED") return existing
        } else {
            val created = exchange("api/v1/web/drafts", "POST", json=
                "{\"name\":${TransportJson.quote(archive.result.packageName)},\"sources\":[{\"id\":\"pending\",\"title\":\"政策待补充\"}]}")
            val draft = created.text("id")
            val token = created.text("capability_token")
            if (!Regex("[a-f0-9]{32}").matches(draft) || !Regex("pt_cap_[A-Za-z0-9_-]{20,200}").matches(token)) {
                throw ServerProbeException("SERVER_RESPONSE_INVALID")
            }
            session = UploadSession(origin, consent.instanceId, draft, token, archive.result.localSetSha256)
            // Save before opening the upload connection. A lost response never
            // discards access to potentially retained remote material.
            sessions.save(session) { cancelled.get() }
        }
        checkCancelled()
        val response = exchange("api/v1/web/drafts/${session.draft}/package-set", "POST", session, file=archive.file)
        verifyReceipt(session, response)
        return get(session) // Fresh server readback, never a local success guess.
    }

    fun refresh(): UploadStatus {
        val caps = capabilities()
        return get(sessions.load(origin, caps.instanceId) ?: throw ServerProbeException("NO_SAVED_UPLOAD"))
    }

    fun delete(): UploadStatus {
        val caps = capabilities()
        val session = sessions.load(origin, caps.instanceId) ?: throw ServerProbeException("NO_SAVED_UPLOAD")
        val response = exchange("api/v1/web/drafts/${session.draft}", "DELETE", session)
        if (response["deleted"] != true || response["cleanup_pending"] !is Boolean) throw ServerProbeException("SERVER_RESPONSE_INVALID")
        // Once an explicit DELETE receipt has been validated, local revocation
        // finishes even if UI cancellation races with this small commit.
        sessions.clear(origin, caps.instanceId)
        return UploadStatus(origin, session.draft, "DELETED", response["cleanup_pending"] == true)
    }

    private fun get(session: UploadSession): UploadStatus {
        val response = exchange("api/v1/web/drafts/${session.draft}", session=session)
        if (response["id"] != session.draft || response["uploaded"] !is Boolean) throw ServerProbeException("SERVER_RESPONSE_INVALID")
        if (response["uploaded"] == true) verifyReceipt(session, response)
        return UploadStatus(origin, session.draft, if (response["uploaded"] == true) "SERVER_CONFIRMED" else "NOT_CONFIRMED")
    }

    private fun verifyReceipt(session: UploadSession, receipt: Map<String, Any?>) {
        try {
            check(receipt["id"] == session.draft && receipt["uploaded"] == true)
            val set = receipt.objectValue("package_set")
            val base = set.objectValue("base")
            check(base["part"] == "BASE" && base["split_name"] == null)
            val raw = set["splits"] as? List<*> ?: error("splits")
            check(raw.size < 101)
            val all = listOf(base) + raw.map { item ->
                val value = item as? Map<*, *> ?: error("split")
                value.entries.associate { (key, value) -> (key as String) to value }
            }
            val parts = all.mapIndexed { index, part ->
                check(part.text("package_name") == set.text("package_name") && part.number("version_code") == set.number("version_code"))
                val split = if (index == 0) null else part.text("split_name").also { check(part["part"] == "SPLIT" && it.isNotBlank()) }
                val digest = part.text("sha256"); check(Regex("[a-f0-9]{64}").matches(digest))
                val size = part.number("size_bytes"); check(size in 1..(150L * 1024 * 1024))
                PartDigest(split, size, digest)
            }
            check(parts.map { it.splitName }.distinct().size == parts.size)
            check(set.number("total_size_bytes") == parts.sumOf { it.bytes })
            check(receiptFingerprint(set.text("package_name"), set.number("version_code"), parts) == session.fingerprint)
        } catch (_: Exception) { throw ServerProbeException("UPLOAD_RECEIPT_MISMATCH") }
    }
}
