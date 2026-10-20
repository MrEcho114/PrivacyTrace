package org.privacytrace.probe

import java.io.IOException
import java.io.InterruptedIOException
import java.net.InetAddress
import java.util.concurrent.Future
import java.util.concurrent.SynchronousQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import okhttp3.Dns

// System DNS may ignore interruption. Bound callers' wait and retain at most one
// outstanding OS lookup, with no queued lookups or growing set of helper threads.
internal class HealthDns(private val source: Dns, private val timeoutMs: Long = 3000) : Dns {
    companion object {
        private val resolver = ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS, SynchronousQueue(),
            { task -> Thread(task, "probe-health-dns").apply { isDaemon = true } }).apply {
            allowCoreThreadTimeOut(true)
        }
    }
    private val cancelled = AtomicBoolean(false)
    private val current = AtomicReference<Future<List<InetAddress>>?>()
    fun cancel() { cancelled.set(true); current.get()?.cancel(true) }

    override fun lookup(hostname: String): List<InetAddress> {
        if (cancelled.get()) throw InterruptedIOException()
        val future = try { resolver.submit<List<InetAddress>> { source.lookup(hostname) } }
        catch (_: Exception) { throw IOException() }
        current.set(future)
        if (cancelled.get()) future.cancel(true)
        try { return future.get(timeoutMs, TimeUnit.MILLISECONDS) }
        catch (_: TimeoutException) { throw InterruptedIOException() }
        catch (_: java.util.concurrent.CancellationException) { throw InterruptedIOException() }
        catch (_: InterruptedException) { Thread.currentThread().interrupt(); throw InterruptedIOException() }
        catch (_: java.util.concurrent.ExecutionException) { throw IOException() }
        finally { future.cancel(true); current.compareAndSet(future, null) }
    }
}
