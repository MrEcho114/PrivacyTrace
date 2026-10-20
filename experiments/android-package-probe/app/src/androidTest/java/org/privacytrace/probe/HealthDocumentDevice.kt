package org.privacytrace.probe

internal fun verifyHealthDocuments() {
    val origin = "https://synthetic.example.test/"
    val valid = "{\"status\":\"ok\",\"version\":\"0.1.0\",\"mode\":\"remote\"}".toByteArray()
    check(decodeHealth(origin, valid) == ServerHealth(origin, "0.1.0", "remote"))
    check(valid.all { it == 0.toByte() })
    val invalid = listOf(
        "{}", "[]", "<html/>",
        "{\"status\":\"ok\",\"version\":1,\"mode\":\"remote\"}",
        "{\"status\":\"ok\",\"version\":\"v\",\"mode\":\"ready\"}",
        "{\"status\":\"ok\",\"status\":\"ok\",\"version\":\"v\",\"mode\":\"remote\"}",
        "{\"status\":\"ok\",\"version\":\"v\",\"mode\":\"remote\",\"secret\":\"ignored?\"}",
        "{\"status\":\"ok\",\"version\":\"${"x".repeat(65)}\",\"mode\":\"remote\"}",
        "{\"status\":\"ok\",\"version\":\"v\",\"mode\":\"remote\"} {}",
        "{status:'ok',version:'v',mode:'remote'}",
    )
    invalid.forEach {
        val bytes = it.toByteArray()
        try { decodeHealth(origin, bytes); error("Expected fixed health JSON refusal") }
        catch (error: ServerProbeException) { check(error.code == "SERVER_RESPONSE_INVALID" && error.cause == null) }
        check(bytes.all { b -> b == 0.toByte() })
    }
    HealthTlsFixture().use { fixture ->
        fixture.server.enqueue(fixture.json())
        val call = HttpsHealthCall(fixture.origin, fixture.client)
        check(decodeHealth(call.origin, call.execute()).mode == "remote")
    }
}
