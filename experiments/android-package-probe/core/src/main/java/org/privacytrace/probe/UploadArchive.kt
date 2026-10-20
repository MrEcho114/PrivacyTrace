package org.privacytrace.probe

import java.io.File
import java.io.FilterInputStream
import java.io.InputStream
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

internal data class UploadCapabilities(
    val instanceId: String, val maxUpload: Long, val maxFile: Long,
    val maxTotal: Long, val maxFiles: Int,
) {
    fun limits() = ProbeLimits(minOf(64, maxFiles), minOf(128L * 1024 * 1024, maxFile),
        minOf(256L * 1024 * 1024, maxTotal, maxUpload))
}

// A private, bounded snapshot prevents an installation update during network I/O
// from mixing bytes from different versions. All temporary APKs die with close().
internal class UploadArchive private constructor(
    private val directory: File, val file: File, val result: ProbeResult,
) : AutoCloseable {
    override fun close() {
        if (!directory.deleteRecursively()) throw ServerProbeException("UPLOAD_CLEANUP_FAILED")
    }
    companion object {
        fun prepare(root: File, source: PackageSource, confirmed: Installation,
                    caps: UploadCapabilities, cancelled: () -> Boolean): UploadArchive {
            val dir = File(root, "pt-upload-${java.util.UUID.randomUUID()}")
            check(dir.mkdir())
            try {
                val copied = mutableListOf<File>()
                val copying = object : PackageSource {
                    override fun snapshot(packageName: String) = source.snapshot(packageName)
                    override fun open(part: InstalledPart): InputStream {
                        val input = source.open(part)
                        val target = File(dir, "part-${copied.size}.apk")
                        copied.add(target)
                        val output = try { target.outputStream() } catch (error: Exception) { input.close(); throw error }
                        return object : FilterInputStream(input) {
                            override fun read(): Int = throw UnsupportedOperationException()
                            override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                                val count = `in`.read(buffer, offset, length)
                                if (count > 0) output.write(buffer, offset, count)
                                return count
                            }
                            override fun close() { try { super.close() } finally { output.close() } }
                        }
                    }
                }
                val result = PackageProbe(copying, caps.limits()).inspectConfirmed(confirmed, cancelled)
                if (copied.size == 1) {
                    if (copied[0].length() > caps.maxUpload) fail(ProbeFailure.LIMIT_EXCEEDED)
                    return UploadArchive(dir, copied[0], result)
                }
                val archive = File(dir, "input.zip")
                ZipOutputStream(archive.outputStream()).use { zip ->
                    copied.forEachIndexed { index, part ->
                        zip.putNextEntry(ZipEntry(if (index == 0) "base.apk" else "part-$index.apk"))
                        part.inputStream().use { input ->
                            val buffer = ByteArray(64 * 1024)
                            while (true) {
                                if (cancelled()) throw ServerProbeException("CANCELLED")
                                val count = input.read(buffer)
                                if (count < 0) break
                                zip.write(buffer, 0, count)
                                if (archive.length() > caps.maxUpload) fail(ProbeFailure.LIMIT_EXCEEDED)
                            }
                        }
                        zip.closeEntry()
                    }
                }
                if (archive.length() > caps.maxUpload) fail(ProbeFailure.LIMIT_EXCEEDED)
                if (cancelled()) throw ServerProbeException("CANCELLED")
                return UploadArchive(dir, archive, result)
            } catch (error: Exception) {
                if (!dir.deleteRecursively()) throw ServerProbeException("UPLOAD_CLEANUP_FAILED")
                throw error
            }
        }
    }
}

// Same local fingerprint as PackageProbe; server receipts are independently
// reconstructed from package identity and every file, never the ZIP checksum.
internal fun receiptFingerprint(packageName: String, version: Long, parts: List<PartDigest>): String {
    val hash = MessageDigest.getInstance("SHA-256")
    fun field(text: String) {
        val bytes = text.toByteArray(Charsets.UTF_8)
        hash.update("${bytes.size}:".toByteArray(Charsets.US_ASCII)); hash.update(bytes)
    }
    field("privacytrace-local-package-probe-v1"); field(packageName); field(version.toString())
    parts.sortedWith(compareBy({ it.splitName != null }, { it.splitName })).forEach {
        field(it.splitName?.let { name -> "split:$name" } ?: "base")
        field(it.bytes.toString()); field(it.sha256)
    }
    return hash.digest().joinToString("") { "%02x".format(it) }
}
