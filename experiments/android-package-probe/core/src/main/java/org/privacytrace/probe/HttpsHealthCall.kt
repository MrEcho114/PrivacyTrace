package org.privacytrace.probe

import java.io.ByteArrayOutputStream
import java.io.InterruptedIOException
import java.io.IOException
import java.net.URI
import java.util.Locale
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.SSLException
import okhttp3.Authenticator
import okhttp3.CookieJar
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Protocol

internal class ServerProbeException(val code: String) : IOException(code)

// A root origin, not a model URL, task URL, or caller-supplied request path.
internal fun analysisOrigin(value: String): String = try {
    require(value.length in 1..1024 && value.all { it.code in 33..126 })
    val uri = URI(value)
    val host = requireNotNull(uri.host)
    require(uri.scheme.equals("https", ignoreCase = true))
    require(uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null)
    require(uri.rawPath.isNullOrEmpty() || uri.rawPath == "/")
    require(uri.port == -1 || uri.port in 1..65535)
    require(Regex(Regex.escape(host) + "(?::[0-9]{1,5})?", RegexOption.IGNORE_CASE).matches(uri.rawAuthority))
    val port = if (uri.port == -1 || uri.port == 443) "" else ":${uri.port}"
    "https://${host.lowercase(Locale.ROOT)}$port/"
} catch (_: Exception) {
    throw ServerProbeException("INVALID_SERVER_ORIGIN")
}

internal fun healthHttpClient(): OkHttpClient = OkHttpClient.Builder()
    // Do not inherit URLConnection authenticators, cookies, or WebView credentials.
    .authenticator(Authenticator.NONE)
    .proxyAuthenticator(Authenticator.NONE)
    .cookieJar(CookieJar.NO_COOKIES)
    .followRedirects(false)
    .followSslRedirects(false)
    .retryOnConnectionFailure(false)
    // No HTTP/2 coalescing/421 follow-up or multiplexed instance connection.
    .protocols(listOf(Protocol.HTTP_1_1))
    .addNetworkInterceptor { chain ->
        val response = chain.proceed(chain.request())
        // OkHttp 4.12 may follow a 503 Retry-After:0 even with retries disabled.
        if (response.code == 429 || response.code == 503) {
            response.close()
            throw ServerProbeException("SERVER_BUSY")
        }
        response
    }
    .connectTimeout(5, TimeUnit.SECONDS)
    .readTimeout(5, TimeUnit.SECONDS)
    .writeTimeout(5, TimeUnit.SECONDS)
    .callTimeout(10, TimeUnit.SECONDS)
    .build()

// The injected client is an internal test seam for a scoped private CA only.
// The product command always uses the default system trust and hostname verifier.
internal class HttpsHealthCall(address: String, client: OkHttpClient = DEFAULT_CLIENT) {
    companion object {
        const val MAX_BODY = 16 * 1024
        private val DEFAULT_CLIENT = healthHttpClient()
    }
    val origin = analysisOrigin(address)
    private val cancelled = AtomicBoolean(false)
    private val dns = HealthDns(client.dns)
    private val call = client.newBuilder().dns(dns).build().newCall(Request.Builder()
        .url(origin + "api/v1/health")
        .get()
        .header("Accept", "application/json")
        .header("Cache-Control", "no-store")
        .header("User-Agent", "PrivacyTrace-Android-Probe")
        .build())

    // OkHttp cancellation is safe from the UI thread; do not wait for network I/O.
    fun cancel() { cancelled.set(true); dns.cancel(); call.cancel() }

    // Raw bytes stay native and bounded. Only the parsed metadata may cross IPC.
    fun execute(): ByteArray = try {
        call.execute().use { response ->
            checkCancelled()
            if (response.code in 300..399) refuse("SERVER_REDIRECT_REJECTED")
            if (response.code == 429 || response.code == 503) refuse("SERVER_BUSY")
            if (response.code != 200) refuse("SERVER_REJECTED")
            val body = response.body ?: refuse("SERVER_RESPONSE_INVALID")
            val media = body.contentType()
            if (media?.type != "application" || media.subtype != "json") refuse("SERVER_RESPONSE_INVALID")
            if (body.contentLength() > MAX_BODY) refuse("SERVER_RESPONSE_TOO_LARGE")
            val output = ByteArrayOutputStream()
            body.byteStream().use { input ->
                val buffer = ByteArray(1024)
                while (true) {
                    checkCancelled()
                    val size = input.read(buffer, 0, minOf(buffer.size, MAX_BODY + 1 - output.size()))
                    if (size < 0) break
                    output.write(buffer, 0, size)
                    if (output.size() > MAX_BODY) refuse("SERVER_RESPONSE_TOO_LARGE")
                }
            }
            checkCancelled()
            output.toByteArray()
        }
    } catch (error: ServerProbeException) {
        throw error
    } catch (_: SSLException) {
        if (cancelled.get()) refuse("CANCELLED") else refuse("SERVER_TLS_REJECTED")
    } catch (_: InterruptedIOException) {
        // A library deadline also cancels its Call, but it is not a user cancellation.
        if (cancelled.get()) refuse("CANCELLED") else refuse("SERVER_TIMEOUT")
    } catch (_: Exception) {
        if (cancelled.get()) refuse("CANCELLED") else refuse("SERVER_UNREACHABLE")
    }

    private fun checkCancelled() { if (cancelled.get()) refuse("CANCELLED") }
    private fun refuse(code: String): Nothing = throw ServerProbeException(code)
}
