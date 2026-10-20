package org.privacytrace.probe

import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import java.io.File
import java.io.FileInputStream
import java.io.IOException

internal data class VisibleApp(val packageName: String, val label: String)

internal class AndroidPackageSource(private val manager: PackageManager) : PackageSource {
    @Suppress("DEPRECATION")
    fun visibleApps(): List<VisibleApp> = manager.queryIntentActivities(
        Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0,
    ).mapNotNull { entry ->
        entry.activityInfo?.let { VisibleApp(it.packageName, entry.loadLabel(manager).toString()) }
    }.distinctBy { it.packageName }.sortedBy { it.label }

    @Suppress("DEPRECATION")
    override fun snapshot(packageName: String): Installation {
        try {
            val info = manager.getPackageInfo(packageName, 0)
            val app = info.applicationInfo ?: fail(ProbeFailure.INCOMPLETE_SET)
            val paths = app.splitSourceDirs?.toList().orEmpty()
            val names = info.splitNames?.toList().orEmpty()
            if (paths.size != names.size) fail(ProbeFailure.INCOMPLETE_SET)
            val parts = listOf(part(null, app.sourceDir ?: fail(ProbeFailure.INCOMPLETE_SET))) +
                names.zip(paths).map { (name, path) -> part(name, path) }
            val version = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
            return Installation(info.packageName, version, info.lastUpdateTime, parts)
        } catch (_: PackageManager.NameNotFoundException) {
            fail(ProbeFailure.NOT_VISIBLE_OR_MISSING)
        } catch (_: SecurityException) {
            fail(ProbeFailure.UNREADABLE)
        }
    }

    private fun part(name: String?, path: String): InstalledPart {
        val file = File(path)
        if (!file.isFile || !file.canRead()) fail(ProbeFailure.UNREADABLE)
        return InstalledPart(name, path, file.length(), file.lastModified())
    }

    override fun open(part: InstalledPart): FileInputStream = try {
        FileInputStream(part.location)
    } catch (_: IOException) {
        fail(ProbeFailure.UNREADABLE)
    } catch (_: SecurityException) {
        fail(ProbeFailure.UNREADABLE)
    }
}
