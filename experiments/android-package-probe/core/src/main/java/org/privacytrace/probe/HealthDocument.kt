package org.privacytrace.probe

import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

internal data class ServerHealth(val origin: String, val version: String, val mode: String)

// Only the health contract's flat string object is accepted. Android JsonReader's
// strict mode still accepts semicolon separators and unknown escapes on API 34.
private class HealthObject(private val text: String) {
    private var at = 0
    private val names = setOf("status", "version", "mode")
    private fun whitespace() { while (at < text.length && text[at] in " \t\r\n") at++ }
    private fun take(expected: Char) {
        whitespace()
        check(at < text.length && text[at++] == expected)
    }
    private fun string(): String {
        take('"')
        val value = StringBuilder()
        while (at < text.length) {
            val char = text[at++]
            if (char == '"') return value.toString()
            check(char.code >= 32)
            value.append(if (char != '\\') char else {
                check(at < text.length)
                when (val escaped = text[at++]) {
                    '"', '\\', '/' -> escaped
                    'b' -> '\b'
                    'f' -> '\u000c'
                    'n' -> '\n'
                    'r' -> '\r'
                    't' -> '\t'
                    'u' -> {
                        check(at + 4 <= text.length)
                        val digits = text.substring(at, at + 4)
                        check(digits.all { it in "0123456789abcdefABCDEF" })
                        at += 4
                        digits.toInt(16).toChar()
                    }
                    else -> error("Invalid JSON escape")
                }
            })
            check(value.length <= 64)
        }
        error("Unterminated JSON string")
    }
    fun fields(): Map<String, String> {
        take('{')
        val result = mutableMapOf<String, String>()
        while (true) {
            val name = string()
            check(name in names && name !in result)
            take(':')
            result[name] = string()
            whitespace()
            check(at < text.length)
            if (text[at] == '}') { at++; break }
            take(',')
        }
        whitespace()
        check(at == text.length && result.keys == names)
        return result
    }
}

// Health metadata is not capability negotiation or permission to upload.
internal fun decodeHealth(origin: String, bytes: ByteArray): ServerHealth {
    try {
        check(bytes.size <= HttpsHealthCall.MAX_BODY)
        val text = Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes)).toString()
        val fields = HealthObject(text).fields()
        check(fields["status"] == "ok")
        val version = checkNotNull(fields["version"])
        check(version.length in 1..64 && version.all { it.code in 33..126 })
        val mode = checkNotNull(fields["mode"])
        check(mode in setOf("remote", "local-jobs"))
        return ServerHealth(origin, version, mode)
    } catch (_: Exception) {
        throw ServerProbeException("SERVER_RESPONSE_INVALID")
    } finally { bytes.fill(0) }
}
