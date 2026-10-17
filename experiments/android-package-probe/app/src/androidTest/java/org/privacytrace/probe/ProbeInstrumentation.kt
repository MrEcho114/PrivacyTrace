package org.privacytrace.probe

import android.app.Activity
import android.app.Instrumentation
import android.os.Bundle

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
        try {
            val packageName = requireNotNull(arguments.getString("probePackage"))
            val expectedParts = requireNotNull(arguments.getString("expectedParts")).toInt()
            require(expectedParts > 0)
            check(android.os.Process.myUid() >= 10000)
            val source = AndroidPackageSource(targetContext.packageManager)
            check(source.visibleApps().any { it.packageName == packageName })
            val first = PackageProbe(source).inspect(packageName)
            val second = PackageProbe(source).inspect(packageName)
            check(first.parts.size == expectedParts)
            check(first == second)
            // No device IDs, inventory, package paths, or APK content in the test receipt.
            output.putString("stream", "PASS: selected visible package, $expectedParts parts, stable digests\n")
            finish(Activity.RESULT_OK, output)
        } catch (_: Exception) {
            output.putString("stream", "FAIL: controlled package probe did not satisfy expectations\n")
            finish(Activity.RESULT_CANCELED, output)
        }
    }
}
