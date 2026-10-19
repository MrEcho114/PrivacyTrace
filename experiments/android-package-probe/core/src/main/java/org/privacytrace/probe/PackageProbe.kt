package org.privacytrace.probe

import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest

// Platform paths stay behind PackageSource. Results contain only the selected package's digests.
internal data class InstalledPart(
    val splitName: String?, val location: String, val bytes: Long, val modifiedMillis: Long,
)

internal data class Installation(
    val packageName: String, val versionCode: Long, val updatedMillis: Long,
    val parts: List<InstalledPart>,
)

internal interface PackageSource {
    fun snapshot(packageName: String): Installation
    fun open(part: InstalledPart): InputStream
}

internal enum class ProbeFailure {
    NOT_VISIBLE_OR_MISSING, UNREADABLE, INCOMPLETE_SET, INSTALLATION_CHANGED,
    LIMIT_EXCEEDED, CANCELLED,
}

// Never include platform exception messages, APK paths, or partial digests in diagnostics.
internal class ProbeException(val failure: ProbeFailure) : Exception(failure.name)

internal data class PartDigest(val splitName: String?, val bytes: Long, val sha256: String)
internal data class ProbeResult(
    val packageName: String, val versionCode: Long, val parts: List<PartDigest>,
    val totalBytes: Long, val localSetSha256: String,
)

internal data class ProbeLimits(
    val maxParts: Int = 64,
    val maxFileBytes: Long = 128L * 1024 * 1024,
    val maxTotalBytes: Long = 256L * 1024 * 1024,
) {
    init { require(maxParts > 0 && maxFileBytes > 0 && maxTotalBytes > 0) }
}

internal class PackageProbe(
    private val source: PackageSource,
    private val limits: ProbeLimits = ProbeLimits(),
) {
    // Metadata only: no APK stream is opened before native confirmation.
    fun prepare(packageName: String): Installation = normalized(source.snapshot(packageName), packageName)

    fun inspect(packageName: String, cancelled: () -> Boolean = { false }): ProbeResult {
        if (cancelled() || Thread.currentThread().isInterrupted) fail(ProbeFailure.CANCELLED)
        return inspectSnapshot(prepare(packageName), cancelled)
    }

    fun inspectConfirmed(confirmed: Installation, cancelled: () -> Boolean = { false }): ProbeResult {
        if (cancelled() || Thread.currentThread().isInterrupted) fail(ProbeFailure.CANCELLED)
        val current = try {
            prepare(confirmed.packageName)
        } catch (_: ProbeException) {
            fail(ProbeFailure.INSTALLATION_CHANGED)
        }
        // Consent belongs to this exact installation metadata, not just the package name.
        if (current != confirmed) fail(ProbeFailure.INSTALLATION_CHANGED)
        return inspectSnapshot(current, cancelled)
    }

    private fun inspectSnapshot(before: Installation, cancelled: () -> Boolean): ProbeResult {
        val packageName = before.packageName
        fun checkCancellation() {
            if (cancelled() || Thread.currentThread().isInterrupted) fail(ProbeFailure.CANCELLED)
        }
        checkCancellation()
        var total = 0L
        val digests = before.parts.map { part ->
            checkCancellation()
            val hash = MessageDigest.getInstance("SHA-256")
            var size = 0L
            try {
                source.open(part).use { input ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        checkCancellation()
                        val count = input.read(buffer)
                        if (count < 0) break
                        if (count == 0) continue
                        if (count.toLong() > limits.maxFileBytes - size ||
                            count.toLong() > limits.maxTotalBytes - total
                        ) fail(ProbeFailure.LIMIT_EXCEEDED)
                        size += count
                        total += count
                        if (size > part.bytes) fail(ProbeFailure.INSTALLATION_CHANGED)
                        hash.update(buffer, 0, count)
                    }
                }
            } catch (_: IOException) {
                fail(ProbeFailure.UNREADABLE)
            } catch (_: SecurityException) {
                fail(ProbeFailure.UNREADABLE)
            }
            if (size != part.bytes) fail(ProbeFailure.INSTALLATION_CHANGED)
            PartDigest(part.splitName, size, hash.digest().hex())
        }
        checkCancellation()
        val after = try {
            normalized(source.snapshot(packageName), packageName)
        } catch (_: ProbeException) {
            fail(ProbeFailure.INSTALLATION_CHANGED)
        }
        if (before != after) fail(ProbeFailure.INSTALLATION_CHANGED)
        checkCancellation()
        // Local PoC fingerprint only: this is deliberately NOT the #70 wire contract.
        val setHash = MessageDigest.getInstance("SHA-256")
        fun field(value: String) {
            val bytes = value.toByteArray(Charsets.UTF_8)
            setHash.update("${bytes.size}:".toByteArray(Charsets.US_ASCII))
            setHash.update(bytes)
        }
        field("privacytrace-local-package-probe-v1")
        field(before.packageName)
        field(before.versionCode.toString())
        digests.forEach {
            field(if (it.splitName == null) "base" else "split:${it.splitName}")
            field(it.bytes.toString())
            field(it.sha256)
        }
        return ProbeResult(packageName, before.versionCode, digests, total, setHash.digest().hex())
    }

    private fun normalized(value: Installation, requestedPackage: String): Installation {
        if (value.packageName != requestedPackage || value.versionCode < 0 ||
            value.parts.isEmpty() || value.parts.count { it.splitName == null } != 1 ||
            value.parts.any { it.location.isBlank() || it.splitName?.isBlank() == true || it.bytes <= 0 } ||
            value.parts.map { it.splitName }.distinct().size != value.parts.size ||
            value.parts.map { it.location }.distinct().size != value.parts.size
        ) fail(ProbeFailure.INCOMPLETE_SET)
        if (value.parts.size > limits.maxParts) fail(ProbeFailure.LIMIT_EXCEEDED)
        var total = 0L
        value.parts.forEach {
            if (it.bytes > limits.maxFileBytes || it.bytes > limits.maxTotalBytes - total) {
                fail(ProbeFailure.LIMIT_EXCEEDED)
            }
            total += it.bytes
        }
        return value.copy(parts = value.parts.sortedWith(compareBy({ it.splitName != null }, { it.splitName })))
    }
}

private fun ByteArray.hex() = joinToString("") { "%02x".format(it) }
internal fun fail(failure: ProbeFailure): Nothing = throw ProbeException(failure)
