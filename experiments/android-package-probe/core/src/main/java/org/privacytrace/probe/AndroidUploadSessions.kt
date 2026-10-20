package org.privacytrace.probe

import android.content.Context
import java.security.MessageDigest

// One retained draft per exact HTTPS origin. Origin-keyed ciphertext/aliases
// never overlap the user's model Key. The authenticated endpoint also pins the
// server's persistent instance UUID, so a reinstalled server fails closed.
internal class AndroidUploadSessions(private val context: Context) : UploadSessions {
    companion object {
        private var swept = false
        private val sweepLock = Any()
        private val accessLock = Any()
    }
    init {
        // Run once per process, before any upload worker exists. Activity
        // recreation must never sweep a cancelled worker that is still draining.
        synchronized(sweepLock) {
            if (!swept) {
                context.cacheDir.listFiles()?.filter {
                    it.isDirectory && Regex("pt-upload-[a-f0-9-]{36}").matches(it.name)
                }?.forEach { check(it.deleteRecursively()) }
                swept = true
            }
        }
    }
    private fun vault(origin: String): ModelConfiguration {
        val name = MessageDigest.getInstance("SHA-256").digest(analysisOrigin(origin).toByteArray())
            .joinToString("") { "%02x".format(it) }
        return ModelConfiguration(AndroidModelConfigFiles(context, "upload-$name.bin"),
            AndroidModelConfigKeys("privacytrace.upload.v1.$name"))
    }
    private fun binding(origin: String, instance: String) = analysisOrigin(origin) + "instance/$instance"

    override fun load(origin: String, instance: String): UploadSession? {
        try {
            val vault = vault(origin)
            val endpoint = vault.status().endpoint ?: return null
            if (endpoint != binding(origin, instance)) throw ServerProbeException("INSTANCE_MISMATCH")
            return vault.withSecret(endpoint) { bytes ->
                val parts = String(bytes, Charsets.US_ASCII).split(':')
                check(parts.size == 3 && Regex("[a-f0-9]{32}").matches(parts[0]) &&
                    Regex("pt_cap_[A-Za-z0-9_-]{20,200}").matches(parts[1]) &&
                    Regex("[a-f0-9]{64}").matches(parts[2]))
                UploadSession(analysisOrigin(origin), instance, parts[0], parts[1], parts[2])
            }
        } catch (error: ServerProbeException) { throw error }
        catch (_: Exception) { throw ServerProbeException("UPLOAD_STORAGE_UNAVAILABLE") }
    }
    override fun save(session: UploadSession, cancelled: () -> Boolean) = synchronized(accessLock) {
        try {
            if (cancelled()) throw ServerProbeException("CANCELLED")
            val vault = vault(session.origin)
            val prepared = vault.prepareSave(binding(session.origin, session.instance),
                "${session.draft}:${session.token}:${session.fingerprint}".toCharArray(), cancelled)
            if (cancelled()) throw ServerProbeException("CANCELLED")
            vault.commitSave(prepared)
            Unit
        } catch (error: ServerProbeException) { throw error }
        catch (_: Exception) { throw ServerProbeException("UPLOAD_STORAGE_UNAVAILABLE") }
    }
    override fun clear(origin: String, instance: String) = synchronized(accessLock) {
        load(origin, instance) // Never delete another instance's retained access.
        try { vault(origin).clear() }
        catch (_: Exception) { throw ServerProbeException("UPLOAD_STORAGE_UNAVAILABLE") }
        Unit
    }

    // Only reachable after a separate native warning/confirmation. This is not
    // a claim that any remote material was deleted or that access is recoverable.
    fun forget(origin: String) = synchronized(accessLock) {
        try { vault(origin).clear() }
        catch (_: Exception) { throw ServerProbeException("UPLOAD_STORAGE_UNAVAILABLE") }
    }
}
