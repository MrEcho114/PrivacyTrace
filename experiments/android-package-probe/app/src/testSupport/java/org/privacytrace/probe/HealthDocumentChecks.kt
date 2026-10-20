package org.privacytrace.probe

enum class HealthDocumentCase {
    VALID_REMOTE, VALID_LOCAL_ESCAPES, EMPTY, ARRAY, HTML, NUMBER_VERSION, BAD_MODE,
    DUPLICATE, UNKNOWN, LONG_VERSION, TRAILING_DOC, LENIENT_OBJECT, SEMICOLON,
    UNKNOWN_ESCAPE, UNESCAPED_TAB, TRAILING_COMMA, INVALID_UNICODE_ESCAPE,
    INVALID_UTF8, EMPTY_STATUS, TLS_DECODE,
}

internal object HealthDocumentChecks {
    fun run(case: HealthDocumentCase) {
        val origin = "https://synthetic.example.test/"
        if (case == HealthDocumentCase.TLS_DECODE) {
            HealthTlsFixture().use { fixture ->
                fixture.server.enqueue(fixture.json())
                val call = HttpsHealthCall(fixture.origin, fixture.client)
                check(decodeHealth(call.origin, call.execute()).mode == "remote")
            }
            return
        }
        val valid = """{"status":"ok","version":"0.1.0","mode":"remote"}"""
        val document = when (case) {
            HealthDocumentCase.VALID_REMOTE -> valid
            HealthDocumentCase.VALID_LOCAL_ESCAPES -> """ { "mode":"local-jobs", "version":"v\u0031", "status":"ok" } """
            HealthDocumentCase.EMPTY -> "{}"
            HealthDocumentCase.ARRAY -> "[]"
            HealthDocumentCase.HTML -> "<html/>"
            HealthDocumentCase.NUMBER_VERSION -> """{"status":"ok","version":1,"mode":"remote"}"""
            HealthDocumentCase.BAD_MODE -> """{"status":"ok","version":"v","mode":"ready"}"""
            HealthDocumentCase.DUPLICATE -> """{"status":"ok","status":"ok","version":"v","mode":"remote"}"""
            HealthDocumentCase.UNKNOWN -> """{"status":"ok","version":"v","mode":"remote","secret":"ignored?"}"""
            HealthDocumentCase.LONG_VERSION -> """{"status":"ok","version":"${"x".repeat(65)}","mode":"remote"}"""
            HealthDocumentCase.TRAILING_DOC -> "$valid {}"
            HealthDocumentCase.LENIENT_OBJECT -> "{status:'ok',version:'v',mode:'remote'}"
            HealthDocumentCase.SEMICOLON -> """{"status":"ok";"version":"v","mode":"remote"}"""
            HealthDocumentCase.UNKNOWN_ESCAPE -> """{"status":"ok","version":"\q","mode":"remote"}"""
            HealthDocumentCase.UNESCAPED_TAB -> "{\"status\":\"ok\",\"version\":\"v\t1\",\"mode\":\"remote\"}"
            HealthDocumentCase.TRAILING_COMMA -> """{"status":"ok","version":"v","mode":"remote",}"""
            HealthDocumentCase.INVALID_UNICODE_ESCAPE -> """{"status":"ok","version":"\u00x1","mode":"remote"}"""
            HealthDocumentCase.INVALID_UTF8 -> valid
            HealthDocumentCase.EMPTY_STATUS -> """{"status":"","version":"v","mode":"remote"}"""
            HealthDocumentCase.TLS_DECODE -> error("Handled above")
        }
        val bytes = document.toByteArray().let {
            if (case == HealthDocumentCase.INVALID_UTF8) it + byteArrayOf(0x80.toByte()) else it
        }
        when (case) {
            HealthDocumentCase.VALID_REMOTE -> check(decodeHealth(origin, bytes) == ServerHealth(origin, "0.1.0", "remote"))
            HealthDocumentCase.VALID_LOCAL_ESCAPES -> check(decodeHealth(origin, bytes) == ServerHealth(origin, "v1", "local-jobs"))
            else -> {
                try { decodeHealth(origin, bytes); error("Expected fixed health JSON refusal") }
                catch (error: ServerProbeException) { check(error.code == "SERVER_RESPONSE_INVALID" && error.cause == null) }
            }
        }
        check(bytes.all { it == 0.toByte() })
    }
}
