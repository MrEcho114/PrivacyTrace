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
            when (arguments.getString("mode")) {
                "https_health" -> {
                    stage = "native_https_health"
                    HealthTlsCase.values().forEach { HealthTlsChecks.run(it) }
                    HealthDnsCase.values().forEach { HealthDnsChecks.run(it) }
                    HealthDocumentCase.values().forEach { HealthDocumentChecks.run(it) }
                    output.putString("stream", "PASS: native HTTPS health TLS15 DNS4 JSON20 ordinary UID\n")
                    finish(Activity.RESULT_OK, output)
                    return
                }
                "model_store" -> {
                    stage = "protected_model_store"
                    runOnMainSync {
                        val input = protectedKeyInput(targetContext)
                        input.setText("synthetic-widget-only-key")
                        check(input.transformationMethod is android.text.method.PasswordTransformationMethod)
                        check(!input.isSaveEnabled && !input.isSaveFromParentEnabled)
                        input.setText("x".repeat(ModelConfiguration.MAX_KEY + 2))
                        check(input.text.length == ModelConfiguration.MAX_KEY + 1)
                        if (android.os.Build.VERSION.SDK_INT >= 26) {
                            check(input.autofillType == android.view.View.AUTOFILL_TYPE_NONE)
                            check(input.autofillValue == null)
                        }
                        input.text.clear()
                    }
                    verifyModelStore(targetContext)
                    output.putString("stream", "PASS: protected model store roundtrip endpoint tamper missing-key interrupted-write delete\n")
                    finish(Activity.RESULT_OK, output)
                    return
                }
                "model_store_seed" -> {
                    stage = "protected_model_seed"
                    seedModelStore(targetContext)
                    output.putString("stream", "PASS: protected model store seeded\n")
                    finish(Activity.RESULT_OK, output)
                    return
                }
                "model_store_reopen" -> {
                    stage = "protected_model_reopen"
                    verifyReopenedModelStore(targetContext)
                    output.putString("stream", "PASS: protected model store reopened and cleared\n")
                    finish(Activity.RESULT_OK, output)
                    return
                }
            }
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
            stage = "confirmation_metadata"
            val probe = PackageProbe(source)
            val confirmed = probe.prepare(packageName)
            check(confirmed.parts.size == expectedParts)
            stage = "first_read"
            val first = probe.inspectConfirmed(confirmed)
            stage = "repeat_read"
            val second = probe.inspectConfirmed(confirmed)
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
