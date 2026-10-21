package org.privacytrace.probe

import android.app.Activity
import android.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

@InvokeArg
class WorkflowArgs { var action: String = ""; var payload: String = "{}" }
@InvokeArg
class CollectPolicyArgs { var model: String = ""; var prompt: String = "" }

@TauriPlugin
class PackageProbePlugin(private var activity: Activity) : Plugin(activity) {
    private var gate = ProbeOperationGate()
    private var worker = Executors.newSingleThreadExecutor()
    private val source = AndroidPackageSource(activity.applicationContext.packageManager)
    private val modelConfig = androidModelConfiguration(activity.applicationContext)
    private val uploadSessions = AndroidUploadSessions(activity.applicationContext)
    private var disposed = false
    // These fields and all Invoke completion calls are confined to the UI thread.
    private var pending: Pending? = null
    private var dialog: AlertDialog? = null
    private var activeOrigin: String? = null

    private class Pending(val invoke: Invoke, val operation: ProbeOperation) {
        var reading = false
        var secret: CharArray? = null
        var healthCall: HttpsHealthCall? = null
        var transport: AnalysisTransport? = null
        var modelCall: ModelPolicyCall? = null
        var capabilities: UploadCapabilities? = null
        var progress: AlertDialog? = null
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
    fun workflow(invoke: Invoke) = activity.runOnUiThread {
        val args = try { invoke.parseArgs(WorkflowArgs::class.java) }
        catch (_: Exception) { invoke.reject("WORKFLOW_INPUT_REJECTED", "WORKFLOW_INPUT_REJECTED"); return@runOnUiThread }
        val origin = activeOrigin
        if (origin == null) { invoke.reject("NO_SAVED_UPLOAD", "NO_SAVED_UPLOAD"); return@runOnUiThread }
        val request = begin(invoke) ?: return@runOnUiThread
        request.reading = true
        val remote = AnalysisTransport(origin, uploadSessions)
        request.transport = remote
        worker.execute {
            try {
                val result = remote.workflow(args.action, args.payload)
                activity.runOnUiThread { finish(request, payload = JSObject().apply { put("json", JSONObject(result).toString()) }) }
            } catch (error: ServerProbeException) {
                activity.runOnUiThread { finish(request, failure = error.code) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "WORKFLOW_INPUT_REJECTED") }
            }
        }
    }

    @Command
    fun collectPolicy(invoke: Invoke) = activity.runOnUiThread {
        if (activeOrigin == null) { invoke.reject("NO_SAVED_UPLOAD", "NO_SAVED_UPLOAD"); return@runOnUiThread }
        val args = try { invoke.parseArgs(CollectPolicyArgs::class.java) }
        catch (_: Exception) { invoke.reject("INVALID_MODEL_REQUEST", "INVALID_MODEL_REQUEST"); return@runOnUiThread }
        if (args.model.isBlank() || args.model.length > 200 || args.prompt.length > 32768) {
            invoke.reject("INVALID_MODEL_REQUEST", "INVALID_MODEL_REQUEST"); return@runOnUiThread
        }
        val request = begin(invoke) ?: return@runOnUiThread
        request.reading = true
        worker.execute {
            try {
                val status = modelConfig.status()
                if (status.endpoint == null) throw ModelConfigException("MODEL_CONFIG_UNAVAILABLE")
                activity.runOnUiThread {
                    request.reading = false
                    if (pending !== request) return@runOnUiThread
                    if (request.operation.cancelled.get()) { finish(request, failure = "CANCELLED"); return@runOnUiThread }
                    dialog = AlertDialog.Builder(activity).setTitle("向个人模型发送收集指令？")
                        .setMessage("目标：${status.endpoint}\n模型：${args.model}\n仅发送页面显示的完整收集指令与应用线索。可能产生费用，结果不保证已联网或取得政策。不会自动重试。")
                        .setNegativeButton("取消") { _, _ -> cancelCurrent() }
                        .setOnCancelListener { cancelCurrent() }
                        .setPositiveButton("确认发送一次") { _, _ ->
                            dialog = null
                            if (pending !== request || request.operation.cancelled.get()) return@setPositiveButton
                            val call = ModelPolicyCall(modelConfig, activeOrigin)
                            request.modelCall = call; request.reading = true
                            worker.execute {
                                try {
                                    val text = call.collect(args.model, args.prompt)
                                    activity.runOnUiThread { finish(request, payload = JSObject().apply { put("text", text) }) }
                                } catch (error: ModelConfigException) {
                                    activity.runOnUiThread { finish(request, failure = error.code) }
                                } catch (_: Exception) {
                                    activity.runOnUiThread { finish(request, failure = "MODEL_REQUEST_FAILED") }
                                }
                            }
                        }.show()
                }
            } catch (error: ModelConfigException) {
                activity.runOnUiThread { finish(request, failure = error.code) }
            }
        }
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
        choose(request)
    }

    private fun choose(request: Pending) {
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
                val confirmed = PackageProbe(source, request.capabilities?.limits() ?: ProbeLimits()).prepare(app.packageName)
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
        val remote = request.transport
        dialog = AlertDialog.Builder(activity)
            .setTitle(if (remote == null) "确认本机读取" else "确认上传所选应用")
            .setMessage("${app.label}\n${app.packageName} · versionCode ${confirmed.versionCode}\n" +
                "${confirmed.parts.size} 个包 · ${confirmed.parts.sumOf { it.bytes }} 字节\n$parts\n\n" +
                if (remote == null) "仅读取上述 base 和全部已安装 splits 的摘要；材料仅留本机，本实验不上传。安装变化后须重新确认。"
                else "目标：${remote.origin}\n实例：${request.capabilities?.instanceId}\n" +
                    "上传上限：${request.capabilities?.maxUpload} 字节（含打包开销）。\n" +
                    "上传完整 base/全部已安装 splits，服务端长期保留至主动删除并受容量约束。" +
                    "仅停止传输不会删除服务器可能已收到的材料；断连后请刷新确认。安装变化后须重新选择。")
            .setNegativeButton("取消") { _, _ -> cancelCurrent() }
            .setOnCancelListener { cancelCurrent() }
            .setPositiveButton(if (remote == null) "开始读取" else "确认上传") { _, _ ->
                if (remote == null) read(request, confirmed) else upload(request, confirmed)
            }
            .show()
    }

    @Command
    fun uploadSelected(invoke: Invoke) = activity.runOnUiThread { uploadCommand(invoke, "upload") }

    @Command
    fun refreshUpload(invoke: Invoke) = activity.runOnUiThread { uploadCommand(invoke, "refresh") }

    @Command
    fun deleteUpload(invoke: Invoke) = activity.runOnUiThread { uploadCommand(invoke, "delete") }

    @Command
    fun forgetUpload(invoke: Invoke) = activity.runOnUiThread { uploadCommand(invoke, "forget") }

    private fun uploadCommand(invoke: Invoke, action: String) {
        val request = begin(invoke) ?: return
        dialog = uploadOriginDialog(activity, when (action) {
            "upload" -> "选择上传实例"; "refresh" -> "刷新上传确认"
            "forget" -> "清除本机访问材料"; else -> "删除远端材料"
        }, submit = { address ->
            dialog = null
            if (pending !== request || request.operation.cancelled.get()) return@uploadOriginDialog
            if (action == "forget") {
                val origin = try { analysisOrigin(address) }
                catch (error: ServerProbeException) { finish(request, failure=error.code); return@uploadOriginDialog }
                dialog = AlertDialog.Builder(activity).setTitle("永久清除本机访问材料？")
                    .setMessage("$origin\n仅清除本机访问材料，不访问服务器，不删除远端材料。" +
                        "若远端删除未确认，材料可能仍被保留。清除后无法找回或再操作旧草稿。")
                    .setNegativeButton("保留访问材料") { _, _ -> cancelCurrent() }
                    .setOnCancelListener { cancelCurrent() }
                    .setPositiveButton("仅清除本机") { _, _ ->
                        if (pending === request && !request.operation.cancelled.get()) {
                            try {
                                uploadSessions.forget(origin)
                                finish(request, payload=uploadPayload(UploadStatus(origin, "", "LOCAL_ACCESS_FORGOTTEN")))
                            } catch (error: ServerProbeException) { finish(request, failure=error.code) }
                        }
                    }.show()
                return@uploadOriginDialog
            }
            val transport = try { AnalysisTransport(address, uploadSessions, stage = { stage ->
                activity.runOnUiThread { showTransferProgress(request, stage) }
            }) }
            catch (error: ServerProbeException) { finish(request, failure = error.code); return@uploadOriginDialog }
            request.transport = transport
            request.reading = true
            worker.execute {
                try {
                    val caps = transport.capabilities()
                    activity.runOnUiThread {
                        if (pending !== request) return@runOnUiThread
                        request.reading = false
                        request.progress?.dismiss()
                        request.progress = null
                        dialog = null
                        if (request.operation.cancelled.get()) finish(request, failure = "CANCELLED")
                        else if (action == "upload") {
                            request.capabilities = caps
                            choose(request)
                        } else if (action == "delete") {
                            dialog = AlertDialog.Builder(activity).setTitle("主动删除远端材料？")
                                .setMessage("${transport.origin}\n实例：${caps.instanceId}\n" +
                                    "删除此实例当前草稿及关联分析。服务器确认后清除本机访问材料。")
                                .setNegativeButton("取消") { _, _ -> cancelCurrent() }
                                .setOnCancelListener { cancelCurrent() }
                                .setPositiveButton("确认删除") { _, _ -> remoteAction(request, true) }.show()
                        } else remoteAction(request, false)
                    }
                } catch (error: ServerProbeException) {
                    activity.runOnUiThread { finish(request, failure = error.code) }
                } catch (_: Exception) {
                    activity.runOnUiThread { finish(request, failure = "UPLOAD_STORAGE_UNAVAILABLE") }
                }
            }
        }, cancel = { cancelCurrent() })
        dialog?.show()
    }

    private fun remoteAction(request: Pending, delete: Boolean) {
        dialog = null
        if (pending !== request || request.operation.cancelled.get()) return
        request.reading = true
        worker.execute {
            try {
                val remote = checkNotNull(request.transport)
                val status = if (delete) remote.delete() else remote.refresh()
                activity.runOnUiThread { finish(request, payload = uploadPayload(status)) }
            } catch (error: ServerProbeException) {
                activity.runOnUiThread { finish(request, failure = error.code) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "UPLOAD_STORAGE_UNAVAILABLE") }
            }
        }
    }

    private fun upload(request: Pending, confirmed: Installation) {
        if (pending !== request || request.operation.cancelled.get()) return
        dialog = null
        request.reading = true
        showTransferProgress(request, "PREPARING")
        worker.execute {
            try {
                val transport = checkNotNull(request.transport)
                val caps = checkNotNull(request.capabilities)
                val status = UploadArchive.prepare(activity.applicationContext.cacheDir, source, confirmed, caps) {
                    request.operation.cancelled.get()
                }.use { archive -> transport.upload(archive, caps) }
                activity.runOnUiThread { finish(request, payload = uploadPayload(status)) }
            } catch (error: ProbeException) {
                activity.runOnUiThread { finish(request, failure = error.failure.name) }
            } catch (error: ServerProbeException) {
                activity.runOnUiThread { finish(request, failure = error.code) }
            } catch (_: Exception) {
                activity.runOnUiThread { finish(request, failure = "UPLOAD_STORAGE_UNAVAILABLE") }
            }
        }
    }

    private fun uploadPayload(status: UploadStatus) = JSObject().apply {
        put("origin", status.origin); put("draft", status.draft)
        put("state", status.state); put("cleanupPending", status.cleanupPending)
    }

    private fun showTransferProgress(request: Pending, stage: String) {
        if (pending !== request || !request.reading || request.operation.cancelled.get()) return
        val message = when (stage) {
            "CHECKING_INSTANCE" -> "正在核对实例与上传能力"
            "PREPARING" -> "正在准备并复核完整安装包集合"
            "CREATING_DRAFT" -> "正在创建本次草稿"
            "PROTECTING_ACCESS" -> "正在加密保存本机访问材料"
            "UPLOADING" -> "正在传输完整包集合"
            "CONFIRMING" -> "正在读回并核对服务器确认"
            "DELETING" -> "正在等待服务器删除确认"
            else -> return
        }
        val progress = request.progress ?: AlertDialog.Builder(activity)
            .setTitle("分析实例操作")
            .setMessage(message)
            .setNegativeButton("停止当前操作") { _, _ -> cancelCurrent() }
            .setOnCancelListener { cancelCurrent() }.create().also {
                request.progress = it; dialog = it; it.show()
            }
        progress.setMessage("$message\n停止传输不会自动删除服务器已收到的材料。")
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
        pending?.transport?.cancel()
        pending?.modelCall?.cancel()
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
        request.transport = null
        request.modelCall = null
        request.progress = null
        pending = null
        dialog?.dismiss()
        dialog = null
        val code = if (!accepted) "CANCELLED" else failure
        if (code != null || payload == null) {
            request.invoke.reject(code ?: "UNREADABLE", code ?: "UNREADABLE")
            return
        }
        if (payload.has("origin") && payload.has("draft") && payload.has("state")) {
            activeOrigin = if (payload.getString("state") in setOf("DELETED", "LOCAL_ACCESS_FORGOTTEN")) null else payload.getString("origin")
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
