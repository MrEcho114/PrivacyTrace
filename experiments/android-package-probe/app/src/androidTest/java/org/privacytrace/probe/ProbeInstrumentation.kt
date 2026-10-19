package org.privacytrace.probe

import android.app.Activity
import android.app.Instrumentation
import android.os.Bundle
import android.os.SystemClock
import java.io.File
import java.io.InputStream

// Optional device smoke test. A missing target or incorrect expected set fails, never skips to green.
class ProbeInstrumentation : Instrumentation() {
    private lateinit var arguments: Bundle

    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        this.arguments = arguments ?: Bundle()
        start()
    }

    override fun onStart() {
        val output = Bundle()
        var stage = "arguments"
        try {
            check(android.os.Process.myUid() >= 10000)
            if (arguments.getString("mode") == "update_race") {
                stage = "installation_update"
                val failure = verifyInstallationUpdate()
                output.putString("stream", "PASS: installation update rejected code=$failure\n")
                finish(Activity.RESULT_OK, output)
                return
            }
            val packageName = requireNotNull(arguments.getString("probePackage"))
            val expectedParts = requireNotNull(arguments.getString("expectedParts")).toInt()
            require(expectedParts > 0)
            val expectedBase = requireNotNull(arguments.getString("expectedBaseSha256"))
            require(expectedBase.matches(Regex("[a-f0-9]{64}")))
            val expectedSplit = arguments.getString("expectedSplitSha256")
            val source = AndroidPackageSource(targetContext.packageManager)
            stage = "visibility"
            check(source.visibleApps().any { it.packageName == packageName })
            stage = "first_read"
            val first = PackageProbe(source).inspect(packageName)
            stage = "repeat_read"
            val second = PackageProbe(source).inspect(packageName)
            stage = "package_count"
            check(first.parts.size == expectedParts)
            stage = "stable_digests"
            check(first == second)
            stage = "artifact_hashes"
            check(first.parts.single { it.splitName == null }.sha256 == expectedBase)
            if (expectedParts == 2) {
                check(first.parts.single { it.splitName == "fixture_feature" }.sha256 == expectedSplit)
            } else check(expectedParts == 1 && expectedSplit == null)
            // No device IDs, inventory, package paths, or APK content in the test receipt.
            output.putString("stream", "PASS: selected visible package, $expectedParts parts, stable digests\nMATCH: installed APK hashes verified\n")
            finish(Activity.RESULT_OK, output)
        } catch (error: Exception) {
            val code = (error as? ProbeException)?.failure?.name ?: "EXPECTATION_FAILED"
            output.putString("stream", "FAIL: controlled package probe stage=$stage code=$code\n")
            finish(Activity.RESULT_CANCELED, output)
        }
    }

    private fun verifyInstallationUpdate(): ProbeFailure {
        val packageName = "org.privacytrace.probe.fixture"
        val beforeVersion = requireNotNull(arguments.getString("beforeVersion")).toLong()
        val afterVersion = requireNotNull(arguments.getString("afterVersion")).toLong()
        require(beforeVersion != afterVersion)
        val source = AndroidPackageSource(targetContext.packageManager)
        check(source.snapshot(packageName).versionCode == beforeVersion)
        val release = File(targetContext.cacheDir, "probe-update-continue")
        release.delete()
        var gated = false
        val gatedSource = object : PackageSource {
            override fun snapshot(packageName: String) = source.snapshot(packageName)
            override fun open(part: InstalledPart): InputStream {
                if (!gated) {
                    gated = true
                    // Test-only scheduling seam: real PackageManager snapshot already captured.
                    sendStatus(1, Bundle().apply { putString("probe_checkpoint", "SNAPSHOT_READY") })
                    val deadline = SystemClock.elapsedRealtime() + 30_000
                    while (!release.exists() && SystemClock.elapsedRealtime() < deadline) {
                        Thread.sleep(25)
                    }
                    check(release.exists())
                }
                return source.open(part)
            }
        }
        try {
            val failure = try {
                PackageProbe(gatedSource).inspect(packageName)
                error("Unexpected complete result")
            } catch (error: ProbeException) {
                error.failure
            }
            check(source.snapshot(packageName).versionCode == afterVersion)
            check(failure == ProbeFailure.INSTALLATION_CHANGED || failure == ProbeFailure.UNREADABLE)
            return failure
        } finally {
            release.delete()
        }
    }
}
