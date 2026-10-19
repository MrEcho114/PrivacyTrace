package org.privacytrace.probe

import android.app.Activity
import android.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import app.tauri.annotation.Command
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

@TauriPlugin
class PackageProbePlugin(private var activity: Activity) : Plugin(activity) {
    private var gate = ProbeOperationGate()
    private var worker = Executors.newSingleThreadExecutor()
    private val source = AndroidPackageSource(activity.applicationContext.packageManager)
    private var disposed = false
    // These fields and all Invoke completion calls are confined to the UI thread.
    private var pending: Pending? = null
    private var dialog: AlertDialog? = null

    private class Pending(val invoke: Invoke, val operation: ProbeOperation) {
        var reading = false
    }

    @Command
    fun inspectSelected(invoke: Invoke) = activity.runOnUiThread {
        val operation = gate.begin()
        if (operation == null) {
            invoke.reject("BUSY_OR_INACTIVE", "BUSY_OR_INACTIVE")
            return@runOnUiThread
        }
        val request = Pending(invoke, operation)
        pending = request
        request.reading = true
        worker.execute {
            try {
                val apps = source.visibleApps()
                activity.runOnUiThread {
                    request.reading = false
                    if (pending !== request) return@runOnUiThread
                    if (operation.cancelled.get()) finish(request, failure = "CANCELLED")
                    else if (apps.isEmpty()) finish(request, failure = "NOT_VISIBLE_OR_MISSING")
                    else {
                        dialog = AlertDialog.Builder(activity)
                            .setTitle("选择要读取的应用")
                            .setItems(apps.map { "${it.label}\n${it.packageName}" }.toTypedArray()) { _, index ->
                                confirm(request, apps[index])
                            }
                            .setNegativeButton("取消") { _, _ -> cancelCurrent() }
                            .setOnCancelListener { cancelCurrent() }
                            .show()
                    }
                }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "UNREADABLE") }
            }
        }
    }

    private fun confirm(request: Pending, app: VisibleApp) {
        if (pending !== request || request.operation.cancelled.get()) return
        dialog = AlertDialog.Builder(activity)
            .setTitle("确认本机读取")
            .setMessage("${app.label}\n${app.packageName}\n\n读取当前 base 和全部已安装 splits 的摘要；材料仅留本机。本实验不上传。")
            .setNegativeButton("取消") { _, _ -> cancelCurrent() }
            .setOnCancelListener { cancelCurrent() }
            .setPositiveButton("开始读取") { _, _ -> read(request, app.packageName) }
            .show()
    }

    private fun read(request: Pending, packageName: String) {
        if (pending !== request || request.operation.cancelled.get()) return
        dialog = null
        request.reading = true
        worker.execute {
            try {
                val result = PackageProbe(source).inspect(packageName) { request.operation.cancelled.get() }
                activity.runOnUiThread { finish(request, result = result) }
            } catch (error: ProbeException) {
                activity.runOnUiThread { finish(request, failure = error.failure.name) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "UNREADABLE") }
            }
        }
    }

    @Command
    fun cancel(invoke: Invoke) = activity.runOnUiThread {
        cancelCurrent()
        invoke.resolve()
    }

    private fun cancelCurrent() {
        gate.cancel()
        dialog?.dismiss()
        dialog = null
        pending?.let { if (!it.reading) finish(it, failure = "CANCELLED") }
    }

    private fun finish(request: Pending, result: ProbeResult? = null, failure: String? = null) {
        if (pending !== request) return
        val accepted = gate.complete(request.operation)
        pending = null
        dialog?.dismiss()
        dialog = null
        val code = if (!accepted) "CANCELLED" else failure
        if (code != null || result == null) {
            request.invoke.reject(code ?: "UNREADABLE", code ?: "UNREADABLE")
            return
        }
        val parts = JSONArray()
        result.parts.forEach {
            parts.put(JSONObject().put("splitName", it.splitName ?: JSONObject.NULL)
                .put("bytes", it.bytes).put("sha256", it.sha256))
        }
        request.invoke.resolve(JSObject().apply {
            put("packageName", result.packageName)
            put("versionCode", result.versionCode.toString())
            put("parts", parts)
            put("totalBytes", result.totalBytes)
            put("localSetSha256", result.localSetSha256)
        })
    }

    override fun onPause(activity: AppCompatActivity) {
        if (activity !== this.activity) return
        gate.pause()
        cancelCurrent()
    }

    override fun onResume(activity: AppCompatActivity) {
        // Tauri can retain a plugin across an Android configuration recreation.
        // Bind dialogs to the current Activity and never revive old read tokens.
        if (activity !== this.activity || disposed) {
            if (!disposed) dispose()
            this.activity = activity
            gate = ProbeOperationGate()
            worker = Executors.newSingleThreadExecutor()
            disposed = false
        }
        gate.resume()
    }

    override fun onDestroy(activity: AppCompatActivity) {
        if (activity === this.activity) dispose()
    }

    private fun dispose() {
        gate.destroy()
        cancelCurrent()
        pending?.let { finish(it, failure = "CANCELLED") }
        worker.shutdownNow()
        disposed = true
    }
}
