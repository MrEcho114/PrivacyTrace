package org.privacytrace.probe

import android.util.JsonReader
import android.util.JsonToken
import java.io.ByteArrayInputStream
import java.io.InputStreamReader

internal data class ServerHealth(val origin: String, val version: String, val mode: String)

// This is health metadata, not capability negotiation or permission to upload.
// Strict streaming parsing avoids coercion, duplicate fields and trailing documents.
internal fun decodeHealth(origin: String, bytes: ByteArray): ServerHealth {
    try {
        check(bytes.size <= HttpsHealthCall.MAX_BODY)
        JsonReader(InputStreamReader(ByteArrayInputStream(bytes), Charsets.UTF_8)).use { reader ->
            reader.isLenient = false
            reader.beginObject()
            val fields = mutableMapOf<String, String>()
            while (reader.hasNext()) {
                val name = reader.nextName()
                check(name in setOf("status", "version", "mode") && name !in fields)
                check(reader.peek() == JsonToken.STRING)
                fields[name] = reader.nextString()
            }
            reader.endObject()
            check(reader.peek() == JsonToken.END_DOCUMENT)
            check(fields.keys == setOf("status", "version", "mode") && fields["status"] == "ok")
            val version = checkNotNull(fields["version"])
            check(version.length in 1..64 && version.all { it.code in 33..126 })
            val mode = checkNotNull(fields["mode"])
            check(mode in setOf("remote", "local-jobs"))
            return ServerHealth(origin, version, mode)
        }
    } catch (_: Exception) {
        throw ServerProbeException("SERVER_RESPONSE_INVALID")
    } finally { bytes.fill(0) }
}
