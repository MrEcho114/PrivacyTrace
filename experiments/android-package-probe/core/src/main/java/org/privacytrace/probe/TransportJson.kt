package org.privacytrace.probe

import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

// Strict JSON: duplicate fields, ambiguous numbers, invalid UTF-8 and trailing
// documents are rejected before a capability or receipt can authorize an action.
internal object TransportJson {
    fun decode(bytes: ByteArray): Map<String, Any?> = try {
        val text = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
        Reader(text).document()
    } catch (_: Exception) { throw ServerProbeException("SERVER_RESPONSE_INVALID") }
    finally { bytes.fill(0) }

    fun quote(value: String): String = buildString {
        append('"')
        value.forEach { c ->
            when (c) {
                '"', '\\' -> { append('\\'); append(c) }
                else -> if (c.code < 32) append("\\u%04x".format(c.code)) else append(c)
            }
        }
        append('"')
    }

    private class Reader(private val text: String) {
        private var at = 0
        private var nodes = 0
        private fun space() { while (at < text.length && text[at] in " \t\r\n") at++ }
        private fun take(c: Char) { space(); check(at < text.length && text[at++] == c) }
        private fun peek(c: Char): Boolean { space(); return at < text.length && text[at] == c }
        private fun string(): String {
            take('"')
            val result = StringBuilder()
            while (at < text.length) {
                val c = text[at++]
                if (c == '"') return result.toString()
                check(c.code >= 32)
                result.append(if (c != '\\') c else {
                    check(at < text.length)
                    when (val escaped = text[at++]) {
                        '"', '\\', '/' -> escaped
                        'b' -> '\b'; 'f' -> '\u000c'; 'n' -> '\n'; 'r' -> '\r'; 't' -> '\t'
                        'u' -> {
                            check(at + 4 <= text.length)
                            val digits = text.substring(at, at + 4)
                            check(digits.all { it in "0123456789abcdefABCDEF" })
                            at += 4
                            digits.toInt(16).toChar()
                        }
                        else -> error("escape")
                    }
                })
            }
            error("string")
        }
        private fun value(depth: Int): Any? {
            check(depth <= 32 && ++nodes <= 20000)
            space()
            check(at < text.length)
            return when (text[at]) {
                '"' -> string()
                '{' -> {
                    take('{')
                    val fields = linkedMapOf<String, Any?>()
                    if (!peek('}')) while (true) {
                        val name = string(); check(!fields.containsKey(name)); take(':')
                        fields[name] = value(depth + 1)
                        if (peek('}')) break
                        take(',')
                    }
                    take('}'); fields
                }
                '[' -> {
                    take('['); val values = mutableListOf<Any?>()
                    if (!peek(']')) while (true) {
                        values.add(value(depth + 1))
                        if (peek(']')) break
                        take(',')
                    }
                    take(']'); values
                }
                't', 'f', 'n' -> {
                    val word = when (text[at]) { 't' -> "true"; 'f' -> "false"; else -> "null" }
                    check(text.startsWith(word, at)); at += word.length
                    when (word) { "true" -> true; "false" -> false; else -> null }
                }
                else -> {
                    val start = at
                    if (text[at] == '-') at++
                    check(at < text.length)
                    if (text[at] == '0') at++ else {
                        check(text[at] in '1'..'9')
                        while (at < text.length && text[at] in '0'..'9') at++
                    }
                    // This transport contract uses only exact 64-bit integers.
                    text.substring(start, at).toLong()
                }
            }
        }
        fun document(): Map<String, Any?> {
            val result = value(0)
            space(); check(at == text.length && result is Map<*, *>)
            return result.entries.associate { (key, value) -> (key as String) to value }
        }
    }
}

internal fun Map<String, Any?>.text(name: String): String =
    this[name] as? String ?: throw ServerProbeException("SERVER_RESPONSE_INVALID")
internal fun Map<String, Any?>.number(name: String): Long =
    this[name] as? Long ?: throw ServerProbeException("SERVER_RESPONSE_INVALID")
internal fun Map<String, Any?>.objectValue(name: String): Map<String, Any?> {
    val value = this[name] as? Map<*, *> ?: throw ServerProbeException("SERVER_RESPONSE_INVALID")
    return value.entries.associate { (key, item) ->
        (key as? String ?: throw ServerProbeException("SERVER_RESPONSE_INVALID")) to item
    }
}
