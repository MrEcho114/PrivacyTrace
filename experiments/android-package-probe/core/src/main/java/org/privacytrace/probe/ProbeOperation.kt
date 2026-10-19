package org.privacytrace.probe

import java.util.concurrent.atomic.AtomicBoolean

// One operation owns the native picker and reader until its worker has drained.
// Cancelling never resets the flag of an older operation when a new one starts.
internal class ProbeOperation {
    val cancelled = AtomicBoolean(false)
}

internal class ProbeOperationGate {
    private var current: ProbeOperation? = null
    private var foreground = true
    private var destroyed = false

    @Synchronized
    fun begin(): ProbeOperation? {
        if (!foreground || destroyed || current != null) return null
        return ProbeOperation().also { current = it }
    }

    @Synchronized
    fun cancel() { current?.cancelled?.set(true) }

    @Synchronized
    fun pause() { foreground = false; cancel() }

    @Synchronized
    fun resume() { if (!destroyed) foreground = true }

    @Synchronized
    fun destroy() { destroyed = true; pause() }

    @Synchronized
    fun complete(operation: ProbeOperation): Boolean {
        if (current !== operation) return false
        current = null
        return foreground && !destroyed && !operation.cancelled.get()
    }
}
