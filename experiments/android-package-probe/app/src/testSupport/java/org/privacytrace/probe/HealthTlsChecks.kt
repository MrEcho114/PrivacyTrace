package org.privacytrace.probe

import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.net.InetAddress
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate

enum class HealthTlsCase {
    ORIGIN_VALIDATION, HTTPS_GET, UNTRUSTED_CERTIFICATE, HOSTNAME_MISMATCH,
    CROSS_ORIGIN_REDIRECT, HTTP_DOWNGRADE, AUTH_CHALLENGE, COOKIE_NOT_REUSED,
    BUSY_RESPONSE, NON_JSON, DECLARED_SIZE_LIMIT, CHUNKED_SIZE_LIMIT,
    DEADLINE_IS_NOT_USER_CANCEL, CANCEL_BEFORE_SEND, CANCEL_IN_FLIGHT,
}

// Generated in memory for every fixture: never commit a test private key or relax global trust.
internal class HealthTlsFixture(host: String = "localhost") : AutoCloseable {
    private val certificate = HeldCertificate.Builder().addSubjectAlternativeName(host).apply {
        // MockWebServer uses an IPv4 loopback URL on some hosts, including Windows.
        if (host == "localhost") addSubjectAlternativeName("127.0.0.1")
    }.build()
    private val serverTls = HandshakeCertificates.Builder().heldCertificate(certificate).build()
    private val clientTls = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
    val client = healthHttpClient().newBuilder()
        .sslSocketFactory(clientTls.sslSocketFactory(), clientTls.trustManager).build()
    val server = MockWebServer().apply {
        useHttps(serverTls.sslSocketFactory(), false)
        start(InetAddress.getByAddress(byteArrayOf(127, 0, 0, 1)), 0)
    }
    val origin: String get() = server.url("/").toString()
    fun json(value: String = "{\"status\":\"ok\",\"version\":\"0.1.0\",\"mode\":\"remote\"}") =
        MockResponse().setHeader("Content-Type", "application/json").setBody(value)
    override fun close() { server.shutdown(); client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown() }
}

internal object HealthTlsChecks {
    private fun expect(code: String, action: () -> Unit) {
        try { action(); error("Expected native HTTPS refusal") } catch (error: ServerProbeException) {
            check(error.code == code && error.message == code && error.cause == null)
        }
    }

    fun run(case: HealthTlsCase) {
        if (case == HealthTlsCase.ORIGIN_VALIDATION) {
            check(analysisOrigin("HTTPS://EXAMPLE.TEST:443/") == "https://example.test/")
            check(analysisOrigin("https://example.test:8443") == "https://example.test:8443/")
            listOf("http://example.test", "https://u:p@example.test", "https://example.test/path",
                "https://example.test?token=x", "https://example.test#x", "https://example.test:",
                "https://example.test:0", " https://example.test", "https://example.test/../").forEach {
                expect("INVALID_SERVER_ORIGIN") { HttpsHealthCall(it) }
            }
            return
        }
        HealthTlsFixture(if (case == HealthTlsCase.HOSTNAME_MISMATCH) "not-localhost.invalid" else "localhost").use { fixture ->
            val server = fixture.server
            when (case) {
                HealthTlsCase.HTTPS_GET -> {
                    server.enqueue(fixture.json())
                    val bytes = HttpsHealthCall(fixture.origin, fixture.client).execute()
                    check(String(bytes, Charsets.UTF_8).contains("0.1.0"))
                    val request = checkNotNull(server.takeRequest(5, TimeUnit.SECONDS))
                    check(request.method == "GET" && request.path == "/api/v1/health" && request.bodySize == 0L)
                    check(request.getHeader("Authorization") == null && request.getHeader("Cookie") == null)
                    check(request.getHeader("User-Agent") == "PrivacyTrace-Android-Probe")
                }
                HealthTlsCase.UNTRUSTED_CERTIFICATE -> {
                    server.enqueue(fixture.json())
                    expect("SERVER_TLS_REJECTED") { HttpsHealthCall(fixture.origin).execute() }
                    check(server.requestCount == 0)
                }
                HealthTlsCase.HOSTNAME_MISMATCH -> {
                    server.enqueue(fixture.json())
                    expect("SERVER_TLS_REJECTED") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                    check(server.requestCount == 0)
                }
                HealthTlsCase.CROSS_ORIGIN_REDIRECT -> HealthTlsFixture().use { other ->
                    other.server.enqueue(other.json())
                    server.enqueue(fixture.json().setResponseCode(302).setHeader("Location", other.origin + "api/v1/health"))
                    expect("SERVER_REDIRECT_REJECTED") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                    check(server.requestCount == 1 && other.server.requestCount == 0)
                }
                HealthTlsCase.HTTP_DOWNGRADE -> {
                    server.enqueue(fixture.json().setResponseCode(307).setHeader("Location", "http://localhost:1/api/v1/health"))
                    expect("SERVER_REDIRECT_REJECTED") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                    check(server.requestCount == 1)
                }
                HealthTlsCase.AUTH_CHALLENGE -> {
                    server.enqueue(fixture.json().setResponseCode(401).setHeader("WWW-Authenticate", "Basic realm=synthetic"))
                    expect("SERVER_REJECTED") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                    check(server.requestCount == 1)
                }
                HealthTlsCase.COOKIE_NOT_REUSED -> {
                    server.enqueue(fixture.json().setHeader("Set-Cookie", "synthetic=private; Secure; Path=/"))
                    server.enqueue(fixture.json())
                    repeat(2) { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                    repeat(2) { check(checkNotNull(server.takeRequest(5, TimeUnit.SECONDS)).getHeader("Cookie") == null) }
                }
                HealthTlsCase.BUSY_RESPONSE -> {
                    for (code in listOf(429, 503)) {
                        server.enqueue(fixture.json().setResponseCode(code).setHeader("Retry-After", "0"))
                        expect("SERVER_BUSY") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                    }
                    check(server.requestCount == 2)
                }
                HealthTlsCase.NON_JSON -> {
                    server.enqueue(MockResponse().setHeader("Content-Type", "text/html").setBody("synthetic HTML"))
                    expect("SERVER_RESPONSE_INVALID") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                }
                HealthTlsCase.DECLARED_SIZE_LIMIT -> {
                    server.enqueue(fixture.json("x".repeat(HttpsHealthCall.MAX_BODY + 1)))
                    expect("SERVER_RESPONSE_TOO_LARGE") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                }
                HealthTlsCase.CHUNKED_SIZE_LIMIT -> {
                    server.enqueue(fixture.json().setChunkedBody("x".repeat(HttpsHealthCall.MAX_BODY + 1), 128))
                    expect("SERVER_RESPONSE_TOO_LARGE") { HttpsHealthCall(fixture.origin, fixture.client).execute() }
                }
                HealthTlsCase.DEADLINE_IS_NOT_USER_CANCEL -> {
                    server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
                    val short = fixture.client.newBuilder().callTimeout(1, TimeUnit.SECONDS).build()
                    try { expect("SERVER_TIMEOUT") { HttpsHealthCall(fixture.origin, short).execute() } }
                    finally { short.connectionPool.evictAll(); short.dispatcher.executorService.shutdown() }
                }
                HealthTlsCase.CANCEL_BEFORE_SEND -> {
                    val call = HttpsHealthCall(fixture.origin, fixture.client)
                    call.cancel()
                    expect("CANCELLED") { call.execute() }
                    check(server.requestCount == 0)
                }
                HealthTlsCase.CANCEL_IN_FLIGHT -> {
                    server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
                    val call = HttpsHealthCall(fixture.origin, fixture.client)
                    val pool = Executors.newSingleThreadExecutor()
                    try {
                        val future = pool.submit { expect("CANCELLED") { call.execute() } }
                        check(server.takeRequest(5, TimeUnit.SECONDS) != null)
                        call.cancel()
                        future.get(5, TimeUnit.SECONDS)
                    } finally { call.cancel(); pool.shutdownNow() }
                }
                HealthTlsCase.ORIGIN_VALIDATION -> error("Handled without a socket")
            }
        }
    }
}
