package org.privacytrace.probe

import java.io.ByteArrayInputStream
import java.io.IOException
import java.io.InputStream
import org.junit.Assert.*
import org.junit.Test

class PackageProbeTest {
    private val base = InstalledPart(null, "/private/base.apk", 3, 10)
    private val split = InstalledPart("config.en", "/private/en.apk", 2, 10)
    private val installation = Installation("org.example.fixture", 7, 100, listOf(base, split))

    private class Source(var value: Installation) : PackageSource {
        var reads = 0
        var opened = 0
        var postRead: (() -> Installation)? = null
        var stream: (InstalledPart) -> InputStream = {
            ByteArrayInputStream(if (it.splitName == null) byteArrayOf(1, 2, 3) else byteArrayOf(4, 5))
        }
        override fun snapshot(packageName: String): Installation {
            reads++
            return if (reads > 1) postRead?.invoke() ?: value else value
        }
        override fun open(part: InstalledPart): InputStream { opened++; return stream(part) }
    }

    private fun expect(code: ProbeFailure, action: () -> Unit) {
        try { action(); fail("Expected $code") } catch (error: ProbeException) {
            assertEquals(code, error.failure)
            assertEquals(code.name, error.message)
            assertNull(error.cause)
        }
    }

    @Test fun `base and all splits have reproducible content digests without paths`() {
        val result = PackageProbe(Source(installation)).inspect(installation.packageName)
        assertEquals(2, result.parts.size)
        assertEquals(5L, result.totalBytes)
        assertEquals("039058c6f2c0cb492c533b0a4d14ef77cc0f78abccced5287d84a1a2011cfb81", result.parts[0].sha256)
        assertEquals(result, PackageProbe(Source(installation)).inspect(installation.packageName))
        assertFalse(result.toString().contains("/private"))
    }

    @Test fun `single APK remains valid`() {
        val result = PackageProbe(Source(installation.copy(parts = listOf(base)))).inspect(installation.packageName)
        assertEquals(1, result.parts.size)
        assertEquals(3L, result.totalBytes)
    }

    @Test fun `enumeration order does not alter result`() {
        val first = PackageProbe(Source(installation)).inspect(installation.packageName)
        val second = PackageProbe(Source(installation.copy(parts = listOf(split, base)))).inspect(installation.packageName)
        assertEquals(first, second)
    }

    @Test fun `incomplete or ambiguous metadata is rejected before opening`() {
        val invalid = listOf(
            emptyList(), listOf(split), listOf(base, base), listOf(base, split, split),
            listOf(base, split.copy(location = base.location)), listOf(base.copy(bytes = 0)),
            listOf(base, split.copy(splitName = "")),
        )
        invalid.forEach { parts ->
            val source = Source(installation.copy(parts = parts))
            expect(ProbeFailure.INCOMPLETE_SET) { PackageProbe(source).inspect(installation.packageName) }
            assertEquals(0, source.opened)
        }
    }

    @Test fun `wrong package cannot supply selected application bytes`() {
        expect(ProbeFailure.INCOMPLETE_SET) {
            PackageProbe(Source(installation)).inspect("org.other.app")
        }
    }

    @Test fun `each installation identity change invalidates complete result`() {
        val changes = listOf(
            installation.copy(versionCode = 8), installation.copy(updatedMillis = 101),
            installation.copy(parts = listOf(base)),
            installation.copy(parts = listOf(base.copy(location = "/new/base.apk"), split)),
            installation.copy(parts = listOf(base.copy(modifiedMillis = 11), split)),
            installation.copy(parts = listOf(base, split.copy(splitName = "config.fr"))),
        )
        changes.forEach { after ->
            val source = Source(installation).apply { postRead = { after } }
            expect(ProbeFailure.INSTALLATION_CHANGED) { PackageProbe(source).inspect(installation.packageName) }
        }
    }

    @Test fun `uninstalled target after read is installation change`() {
        val source = Source(installation).apply { postRead = { throw ProbeException(ProbeFailure.NOT_VISIBLE_OR_MISSING) } }
        expect(ProbeFailure.INSTALLATION_CHANGED) { PackageProbe(source).inspect(installation.packageName) }
    }

    @Test fun `invisible and missing are not confused with an empty complete set`() {
        val source = object : PackageSource {
            override fun snapshot(packageName: String): Installation = throw ProbeException(ProbeFailure.NOT_VISIBLE_OR_MISSING)
            override fun open(part: InstalledPart): InputStream = error("Must not open")
        }
        expect(ProbeFailure.NOT_VISIBLE_OR_MISSING) { PackageProbe(source).inspect(installation.packageName) }
    }

    @Test fun `unreadable part closes stream and does not expose diagnostic path`() {
        var closed = false
        val source = Source(installation).apply {
            stream = { object : InputStream() {
                override fun read(): Int = throw IOException("/private/base.apk secret")
                override fun close() { closed = true }
            } }
        }
        expect(ProbeFailure.UNREADABLE) { PackageProbe(source).inspect(installation.packageName) }
        assertTrue(closed)
    }

    @Test fun `short and growing streams cannot pass metadata size check`() {
        listOf(byteArrayOf(1), byteArrayOf(1, 2, 3, 4)).forEach { bytes ->
            val source = Source(installation).apply { stream = { ByteArrayInputStream(bytes) } }
            expect(ProbeFailure.INSTALLATION_CHANGED) { PackageProbe(source).inspect(installation.packageName) }
        }
    }

    @Test fun `part file and total limits reject before reading including overflow sizes`() {
        listOf(
            ProbeLimits(maxParts = 1), ProbeLimits(maxFileBytes = 2), ProbeLimits(maxTotalBytes = 4),
        ).forEach { limits ->
            val source = Source(installation)
            expect(ProbeFailure.LIMIT_EXCEEDED) { PackageProbe(source, limits).inspect(installation.packageName) }
            assertEquals(0, source.opened)
        }
        expect(ProbeFailure.LIMIT_EXCEEDED) {
            PackageProbe(Source(installation.copy(parts = listOf(base.copy(bytes = Long.MAX_VALUE), split))))
                .inspect(installation.packageName)
        }
    }

    @Test fun `stream growth cannot exceed byte budget`() {
        val source = Source(installation.copy(parts = listOf(base))).apply {
            stream = { ByteArrayInputStream(byteArrayOf(1, 2, 3, 4)) }
        }
        expect(ProbeFailure.LIMIT_EXCEEDED) {
            PackageProbe(source, ProbeLimits(maxFileBytes = 3, maxTotalBytes = 3)).inspect(installation.packageName)
        }
    }

    @Test fun `cancel before and during read closes without returning partial results`() {
        val source = Source(installation)
        expect(ProbeFailure.CANCELLED) { PackageProbe(source).inspect(installation.packageName) { true } }
        assertEquals(0, source.opened)
        var cancel = false
        var closed = false
        source.stream = { object : ByteArrayInputStream(byteArrayOf(1, 2, 3)) {
            override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                cancel = true
                return super.read(buffer, offset, length)
            }
            override fun close() { closed = true; super.close() }
        } }
        expect(ProbeFailure.CANCELLED) { PackageProbe(source).inspect(installation.packageName) { cancel } }
        assertTrue(closed)
    }

    @Test fun `same bytes in a different split identity alter local fingerprint`() {
        val first = PackageProbe(Source(installation)).inspect(installation.packageName)
        val other = PackageProbe(Source(installation.copy(parts = listOf(base, split.copy(splitName = "config.fr")))))
            .inspect(installation.packageName)
        assertNotEquals(first.localSetSha256, other.localSetSha256)
    }

    @Test fun `confirmation prepares the bounded complete set without reading APK bytes`() {
        val source = Source(installation.copy(parts = listOf(split, base)))
        val confirmed = PackageProbe(source).prepare(installation.packageName)
        assertEquals(installation, confirmed)
        assertEquals(5L, confirmed.parts.sumOf { it.bytes })
        assertEquals(0, source.opened)
        expect(ProbeFailure.LIMIT_EXCEEDED) {
            PackageProbe(source, ProbeLimits(maxTotalBytes = 4)).prepare(installation.packageName)
        }
        assertEquals(0, source.opened)
    }

    @Test fun `unchanged confirmation reads exactly the displayed set regardless of enumeration order`() {
        val source = Source(installation)
        val probe = PackageProbe(source)
        val confirmed = probe.prepare(installation.packageName)
        source.value = installation.copy(parts = listOf(split, base))
        val result = probe.inspectConfirmed(confirmed)
        assertEquals(confirmed.parts.size, result.parts.size)
        assertEquals(confirmed.parts.sumOf { it.bytes }, result.totalBytes)
        assertEquals(2, source.opened)
    }

    @Test fun `changed installation since confirmation requires new consent before any stream opens`() {
        val changes = listOf(
            installation.copy(versionCode = 8), installation.copy(updatedMillis = 101),
            installation.copy(parts = listOf(base)),
            installation.copy(parts = listOf(base.copy(location = "/new/base.apk"), split)),
            installation.copy(parts = listOf(base.copy(modifiedMillis = 11), split)),
            installation.copy(parts = listOf(base.copy(bytes = 4), split)),
            installation.copy(parts = listOf(base, split.copy(splitName = "config.fr"))),
        )
        changes.forEach { changed ->
            val source = Source(installation)
            val probe = PackageProbe(source)
            val confirmed = probe.prepare(installation.packageName)
            source.value = changed
            expect(ProbeFailure.INSTALLATION_CHANGED) { probe.inspectConfirmed(confirmed) }
            assertEquals(0, source.opened)
        }
    }

    @Test fun `missing or unreadable installation after confirmation never opens a stream`() {
        listOf(ProbeFailure.NOT_VISIBLE_OR_MISSING, ProbeFailure.UNREADABLE).forEach { failure ->
            val confirmed = PackageProbe(Source(installation)).prepare(installation.packageName)
            val source = object : PackageSource {
                override fun snapshot(packageName: String): Installation = throw ProbeException(failure)
                override fun open(part: InstalledPart): InputStream = error("Must not open")
            }
            expect(ProbeFailure.INSTALLATION_CHANGED) { PackageProbe(source).inspectConfirmed(confirmed) }
        }
    }

    @Test fun `confirmation still rejects installation changes during reading`() {
        val source = Source(installation).apply {
            postRead = { if (opened > 0) installation.copy(updatedMillis = 101) else installation }
        }
        val probe = PackageProbe(source)
        val confirmed = probe.prepare(installation.packageName)
        expect(ProbeFailure.INSTALLATION_CHANGED) { probe.inspectConfirmed(confirmed) }
        assertEquals(2, source.opened)
    }

    @Test fun `cancelled confirmation cannot read or return a partial result`() {
        val source = Source(installation)
        val probe = PackageProbe(source)
        val confirmed = probe.prepare(installation.packageName)
        expect(ProbeFailure.CANCELLED) { probe.inspectConfirmed(confirmed) { true } }
        assertEquals(0, source.opened)
    }
}
