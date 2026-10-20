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
    private val modelConfig = androidModelConfiguration(activity.applicationContext)
    private var disposed = false
    // These fields and all Invoke completion calls are confined to the UI thread.
    private var pending: Pending? = null
    private var dialog: AlertDialog? = null

    private class Pending(val invoke: Invoke, val operation: ProbeOperation) {
        var reading = false
        var secret: CharArray? = null
        var healthCall: HttpsHealthCall? = null
    }

    private fun begin(invoke: Invoke): Pending? {
        val operation = gate.begin()
        if (operation == null) {
            invoke.reject("BUSY_OR_INACTIVE", "BUSY_OR_INACTIVE")
            return null
        }
        return Pending(invoke, operation).also { pending = it }
    }

    @Command
    fun checkServer(invoke: Invoke) = activity.runOnUiThread {
        val request = begin(invoke) ?: return@runOnUiThread
        dialog = serverHealthDialog(activity,
            check = { address -> checkHealth(request, address) },
            cancel = { cancelCurrent() })
        dialog?.show()
    }

    private fun checkHealth(request: Pending, address: String) {
        dialog = null
        if (pending !== request || request.operation.cancelled.get()) return
        val call = try { HttpsHealthCall(address) }
        catch (error: ServerProbeException) {
            finish(request, failure = error.code)
            return
        }
        request.healthCall = call
        request.reading = true
        worker.execute {
            try {
                val health = decodeHealth(call.origin, call.execute())
                activity.runOnUiThread {
                    finish(request, payload = JSObject().apply {
                        put("origin", health.origin)
                        put("version", health.version)
                        put("mode", health.mode)
                        put("scope", "HEALTH_ONLY")
                    })
                }
            } catch (error: ServerProbeException) {
                activity.runOnUiThread { finish(request, failure = error.code) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "SERVER_UNREACHABLE") }
            }
        }
    }

    @Command
    fun modelStatus(invoke: Invoke) = activity.runOnUiThread {
        val request = begin(invoke) ?: return@runOnUiThread
        request.reading = true
        worker.execute {
            try {
                val status = modelConfig.status()
                activity.runOnUiThread { finish(request, payload = modelPayload(status)) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "MODEL_CONFIG_UNAVAILABLE") }
            }
        }
    }

    @Command
    fun configureModel(invoke: Invoke) = activity.runOnUiThread {
        val request = begin(invoke) ?: return@runOnUiThread
        request.reading = true
        worker.execute {
            try {
                val status = modelConfig.status()
                activity.runOnUiThread {
                    request.reading = false
                    if (pending !== request) return@runOnUiThread
                    if (request.operation.cancelled.get()) finish(request, failure = "CANCELLED")
                    else {
                        dialog = modelConfigDialog(activity, status,
                            save = { address, secret -> saveModel(request, address, secret) },
                            cancel = { cancelCurrent() })
                        dialog?.show()
                    }
                }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "MODEL_CONFIG_UNAVAILABLE") }
            }
        }
    }

    private fun saveModel(request: Pending, address: String, secret: CharArray) {
        dialog = null
        if (pending !== request || request.operation.cancelled.get()) {
            secret.fill('\u0000')
            return
        }
        request.reading = true
        request.secret = secret
        worker.execute {
            try {
                val prepared = modelConfig.prepareSave(address, secret) { request.operation.cancelled.get() }
                activity.runOnUiThread {
                    if (pending !== request) return@runOnUiThread
                    if (request.operation.cancelled.get()) finish(request, failure = "CANCELLED")
                    else try {
                        // Serialized with lifecycle cancellation and Invoke completion.
                        finish(request, payload = modelPayload(modelConfig.commitSave(prepared)))
                    } catch (_: Exception) {
                        finish(request, failure = "MODEL_CONFIG_UNAVAILABLE")
                    }
                }
            } catch (error: ModelConfigException) {
                activity.runOnUiThread { finish(request, failure = error.code) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "MODEL_CONFIG_UNAVAILABLE") }
            } finally {
                secret.fill('\u0000')
            }
        }
    }

    @Command
    fun clearModel(invoke: Invoke) = activity.runOnUiThread {
        val request = begin(invoke) ?: return@runOnUiThread
        dialog = AlertDialog.Builder(activity)
            .setTitle("删除本机模型配置？")
            .setMessage("删除本机保存的模型地址、加密 Key 和包装密钥。之后需要重新输入。")
            .setNegativeButton("取消") { _, _ -> cancelCurrent() }
            .setOnCancelListener { cancelCurrent() }
            .setPositiveButton("确认删除") { _, _ ->
                dialog = null
                if (pending === request && !request.operation.cancelled.get()) {
                    try { finish(request, payload = modelPayload(modelConfig.clear())) }
                    catch (_: Exception) { finish(request, failure = "MODEL_CONFIG_UNAVAILABLE") }
                }
            }.show()
    }

    @Command
    fun inspectSelected(invoke: Invoke) = activity.runOnUiThread {
        val request = begin(invoke) ?: return@runOnUiThread
        request.reading = true
        worker.execute {
            try {
                val apps = source.visibleApps()
                activity.runOnUiThread {
                    request.reading = false
                    if (pending !== request) return@runOnUiThread
                    if (request.operation.cancelled.get()) finish(request, failure = "CANCELLED")
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
        dialog = null
        request.reading = true
        worker.execute {
            try {
                val confirmed = PackageProbe(source).prepare(app.packageName)
                activity.runOnUiThread {
                    request.reading = false
                    if (pending !== request) return@runOnUiThread
                    if (request.operation.cancelled.get()) finish(request, failure = "CANCELLED")
                    else showConfirmation(request, app, confirmed)
                }
            } catch (error: ProbeException) {
                activity.runOnUiThread { finish(request, failure = error.failure.name) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "UNREADABLE") }
            }
        }
    }

    private fun showConfirmation(request: Pending, app: VisibleApp, confirmed: Installation) {
        val parts = confirmed.parts.joinToString("\n") { "${it.splitName ?: "base"} · ${it.bytes} 字节" }
        dialog = AlertDialog.Builder(activity)
            .setTitle("确认本机读取")
            .setMessage("${app.label}\n${app.packageName} · versionCode ${confirmed.versionCode}\n" +
                "${confirmed.parts.size} 个包 · ${confirmed.parts.sumOf { it.bytes }} 字节\n$parts\n\n" +
                "仅读取上述 base 和全部已安装 splits 的摘要；材料仅留本机，本实验不上传。安装变化后须重新确认。")
            .setNegativeButton("取消") { _, _ -> cancelCurrent() }
            .setOnCancelListener { cancelCurrent() }
            .setPositiveButton("开始读取") { _, _ -> read(request, confirmed) }
            .show()
    }

    private fun read(request: Pending, confirmed: Installation) {
        if (pending !== request || request.operation.cancelled.get()) return
        dialog = null
        request.reading = true
        worker.execute {
            try {
                val result = PackageProbe(source).inspectConfirmed(confirmed) { request.operation.cancelled.get() }
                activity.runOnUiThread { finish(request, payload = probePayload(result)) }
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
        pending?.healthCall?.cancel()
        pending?.secret?.fill('\u0000')
        dialog?.dismiss()
        dialog = null
        pending?.let { if (!it.reading) finish(it, failure = "CANCELLED") }
    }

    private fun finish(request: Pending, payload: JSObject? = null, failure: String? = null) {
        if (pending !== request) return
        val accepted = gate.complete(request.operation)
        request.secret?.fill('\u0000')
        request.secret = null
        request.healthCall = null
        pending = null
        dialog?.dismiss()
        dialog = null
        val code = if (!accepted) "CANCELLED" else failure
        if (code != null || payload == null) {
            request.invoke.reject(code ?: "UNREADABLE", code ?: "UNREADABLE")
            return
        }
        request.invoke.resolve(payload)
    }

    private fun modelPayload(status: ModelConfigStatus) = JSObject().apply {
        put("configured", status.endpoint != null)
        put("endpoint", status.endpoint ?: JSONObject.NULL)
    }

    private fun probePayload(result: ProbeResult): JSObject {
        val parts = JSONArray()
        result.parts.forEach {
            parts.put(JSONObject().put("splitName", it.splitName ?: JSONObject.NULL)
                .put("bytes", it.bytes).put("sha256", it.sha256))
        }
        return JSObject().apply {
            put("packageName", result.packageName)
            put("versionCode", result.versionCode.toString())
            put("parts", parts)
            put("totalBytes", result.totalBytes)
            put("localSetSha256", result.localSetSha256)
        }
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
