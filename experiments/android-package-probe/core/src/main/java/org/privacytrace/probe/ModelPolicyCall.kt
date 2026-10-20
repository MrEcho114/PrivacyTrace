package org.privacytrace.probe

import java.io.ByteArrayOutputStream
import java.net.URI
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import javax.net.ssl.SSLException
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** Only the configured model endpoint receives this request. No APK or task capability. */
internal class ModelPolicyCall(private val configuration: ModelConfiguration,
    private val analysis: String?, client: OkHttpClient = healthHttpClient()) {
    private val cancelled = AtomicBoolean(false)
    private val active = AtomicReference<Call?>()
    private val dns = HealthDns(client.dns)
    private val http = client.newBuilder().dns(dns).readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS).callTimeout(90, TimeUnit.SECONDS).build()

    fun cancel() { cancelled.set(true); dns.cancel(); active.get()?.cancel() }
    private fun checkActive() { if (cancelled.get()) throw ModelConfigException("CANCELLED") }

    fun collect(model: String, prompt: String): String {
        checkActive()
        if (model.isBlank() || model.length > 200 || model.any { it.code < 32 } ||
            prompt.isBlank() || prompt.toByteArray(Charsets.UTF_8).size > 32 * 1024) {
            throw ModelConfigException("INVALID_MODEL_REQUEST")
        }
        val endpoint = configuration.status().endpoint ?: throw ModelConfigException("MODEL_CONFIG_UNAVAILABLE")
        val target = URI(endpoint)
        if (analysis != null && analysisOrigin("${target.scheme}://${target.rawAuthority}/") == analysis) {
            throw ModelConfigException("MODEL_ANALYSIS_ORIGIN_REJECTED")
        }
        // The full endpoint is bound by the encrypted configuration. Never append
        // paths or take an endpoint/key/headers from JavaScript.
        return configuration.withSecret(endpoint) { key ->
            checkActive()
            val body = "{\"model\":${TransportJson.quote(model)},\"stream\":false,\"max_tokens\":8192," +
                "\"messages\":[{\"role\":\"user\",\"content\":${TransportJson.quote(prompt)}}]}"
            val secret = String(key, Charsets.US_ASCII)
            val call = http.newCall(Request.Builder().url(endpoint).post(body.toRequestBody("application/json".toMediaType()))
                .header("Authorization", "Bearer $secret").header("Accept", "application/json")
                .header("Cache-Control", "no-store").build())
            active.set(call)
            if (cancelled.get()) call.cancel()
            try {
                call.execute().use { response ->
                    checkActive()
                    when {
                        response.code in 300..399 -> throw ModelConfigException("MODEL_REDIRECT_REJECTED")
                        response.code == 429 || response.code == 503 -> throw ModelConfigException("MODEL_BUSY")
                        response.code !in 200..299 -> throw ModelConfigException("MODEL_REQUEST_REJECTED")
                    }
                    val content = response.body ?: throw ModelConfigException("MODEL_RESPONSE_INVALID")
                    if (content.contentType()?.type != "application" || content.contentType()?.subtype != "json" ||
                        content.contentLength() > 1024 * 1024) throw ModelConfigException("MODEL_RESPONSE_INVALID")
                    val output = ByteArrayOutputStream()
                    content.byteStream().use { stream ->
                        val buffer = ByteArray(8192)
                        while (true) {
                            checkActive()
                            val count = stream.read(buffer)
                            if (count < 0) break
                            if (output.size() + count > 1024 * 1024) throw ModelConfigException("MODEL_RESPONSE_INVALID")
                            output.write(buffer, 0, count)
                        }
                    }
                    val result = TransportJson.decode(output.toByteArray(), allowDecimals = true)
                    val choice = (result["choices"] as? List<*>)?.singleOrNull() as? Map<*, *>
                        ?: throw ModelConfigException("MODEL_RESPONSE_INVALID")
                    if (choice["finish_reason"] != "stop") throw ModelConfigException("MODEL_RESPONSE_INCOMPLETE")
                    val text = (choice["message"] as? Map<*, *>)?.get("content") as? String
                        ?: throw ModelConfigException("MODEL_RESPONSE_INVALID")
                    if (text.isBlank() || text.contains(secret)) throw ModelConfigException("MODEL_RESPONSE_INVALID")
                    checkActive()
                    text
                }
            } catch (error: ModelConfigException) { throw error }
            catch (error: ServerProbeException) {
                checkActive()
                throw ModelConfigException(if (error.code == "SERVER_BUSY") "MODEL_BUSY" else "MODEL_RESPONSE_INVALID")
            }
            catch (_: SSLException) { throw ModelConfigException("MODEL_TLS_REJECTED") }
            catch (_: Exception) { checkActive(); throw ModelConfigException("MODEL_REQUEST_FAILED") }
            finally { active.compareAndSet(call, null) }
        }
    }
}
