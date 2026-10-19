package org.privacytrace.probe

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class ProbeActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val cancelled = AtomicBoolean(false)
    private val busy = AtomicBoolean(false)
    private lateinit var status: TextView
    private lateinit var choices: LinearLayout
    private var confirmation: AlertDialog? = null
    private val source by lazy { AndroidPackageSource(packageManager) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val padding = (16 * resources.displayMetrics.density).toInt()
            setPadding(padding, padding, padding, padding)
        }
        body.addView(TextView(this).apply { setText(R.string.notice); textSize = 18f })
        body.addView(Button(this).apply {
            setText(R.string.list_apps)
            setOnClickListener { listApps() }
        })
        body.addView(Button(this).apply {
            setText(R.string.cancel)
            setOnClickListener { cancelRead() }
        })
        status = TextView(this).apply { setTextIsSelectable(true); textSize = 16f }
        choices = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        body.addView(status)
        body.addView(choices)
        setContentView(ScrollView(this).apply { addView(body) })
    }

    private fun listApps() = runWork {
        val apps = source.visibleApps()
        show {
            status.text = if (apps.isEmpty()) getString(R.string.empty) else ""
            choices.removeAllViews()
            apps.forEach { app ->
                choices.addView(Button(this).apply {
                    text = getString(R.string.app_choice, app.label, app.packageName)
                    isAllCaps = false
                    setOnClickListener {
                        if (!busy.get()) confirm(app)
                    }
                })
            }
        }
    }

    private fun confirm(app: VisibleApp) = runWork {
        val probe = PackageProbe(source)
        val confirmed = probe.prepare(app.packageName)
        val parts = confirmed.parts.joinToString("\n") { "${it.splitName ?: "base"} · ${it.bytes} 字节" }
        show {
            confirmation = AlertDialog.Builder(this)
                .setTitle(R.string.confirm_title)
                .setMessage(getString(
                    R.string.confirm_body, app.label, app.packageName, confirmed.versionCode.toString(),
                    confirmed.parts.size, confirmed.parts.sumOf { it.bytes }, parts,
                ))
                .setNegativeButton(R.string.dismiss) { _, _ -> cancelRead() }
                .setOnCancelListener { cancelRead() }
                .setPositiveButton(R.string.confirm) { _, _ ->
                    confirmation = null
                    choices.removeAllViews()
                    runWork {
                        val result = probe.inspectConfirmed(confirmed) { cancelled.get() }
                        val parts = result.parts.joinToString("\n\n") {
                            "${it.splitName ?: "base"} · ${it.bytes}\n${it.sha256}"
                        }
                        show {
                            status.text = getString(
                                R.string.result, result.packageName, result.versionCode.toString(),
                                result.parts.size, result.totalBytes, result.localSetSha256, parts,
                            )
                        }
                    }
                }.show()
        }
    }

    private fun cancelRead() {
        cancelled.set(true)
        confirmation?.dismiss()
        confirmation = null
        choices.removeAllViews()
        status.text = getString(R.string.error, ProbeFailure.CANCELLED.name)
    }

    private fun runWork(action: () -> Unit) {
        if (!busy.compareAndSet(false, true)) return
        cancelled.set(false)
        status.setText(R.string.working)
        worker.execute {
            try {
                action()
            } catch (error: ProbeException) {
                show { status.text = getString(R.string.error, error.failure.name) }
            } catch (_: Exception) {
                show { status.setText(R.string.unexpected_error) }
            } finally {
                // Release on the UI queue after delivering this operation's result.
                runOnUiThread { busy.set(false) }
            }
        }
    }

    private fun show(action: () -> Unit) = runOnUiThread {
        if (!isDestroyed && !isFinishing) {
            if (cancelled.get()) {
                choices.removeAllViews()
                status.text = getString(R.string.error, ProbeFailure.CANCELLED.name)
            } else action()
        }
    }

    override fun onStop() {
        if (confirmation != null || busy.get()) cancelRead() else cancelled.set(true)
        super.onStop()
    }

    override fun onDestroy() {
        worker.shutdownNow()
        super.onDestroy()
    }
}
