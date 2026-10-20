package org.privacytrace.probe

import java.io.IOException
import java.io.InterruptedIOException
import java.net.InetAddress
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import okhttp3.Dns

enum class HealthDnsCase { SUCCESS, CANCEL_BEFORE, CANCEL_IN_FLIGHT, TIMEOUT_AND_SATURATION }

internal object HealthDnsChecks {
    private fun dns(lookup: () -> List<InetAddress>) = object : Dns {
        override fun lookup(hostname: String) = lookup()
    }
    private fun ready(): List<InetAddress> {
        // A just-completed task can briefly retain the no-queue worker slot.
        repeat(100) {
            try { return HealthDns(dns { listOf(InetAddress.getByAddress(byteArrayOf(127, 0, 0, 1))) }).lookup("synthetic.test") }
            catch (_: IOException) { Thread.sleep(10) }
        }
        error("DNS test worker did not become available")
    }
    fun run(case: HealthDnsCase) {
        check(ready().single().isLoopbackAddress)
        if (case == HealthDnsCase.SUCCESS) return
        if (case == HealthDnsCase.CANCEL_BEFORE) {
            val resolver = HealthDns(dns { error("Cancelled lookup must not start") })
            resolver.cancel()
            try { resolver.lookup("synthetic.test"); error("Expected DNS cancellation") }
            catch (_: InterruptedIOException) { return }
        }
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val exited = CountDownLatch(1)
        val resolver = HealthDns(dns {
            entered.countDown()
            try {
                // Emulate an OS lookup that ignores interruption until explicitly released.
                while (release.count != 0L) {
                    try { release.await() } catch (_: InterruptedException) { /* OS-like blocking */ }
                }
                listOf(InetAddress.getByAddress(byteArrayOf(127, 0, 0, 1)))
            } finally { exited.countDown() }
        }, if (case == HealthDnsCase.TIMEOUT_AND_SATURATION) 100 else 3000)
        val caller = Executors.newSingleThreadExecutor()
        try {
            val outcome = caller.submit<Boolean> {
                try { resolver.lookup("synthetic.test"); false }
                catch (_: InterruptedIOException) { true }
            }
            check(entered.await(2, TimeUnit.SECONDS))
            if (case == HealthDnsCase.CANCEL_IN_FLIGHT) resolver.cancel()
            check(outcome.get(2, TimeUnit.SECONDS))
            val unexpectedLookup = AtomicBoolean(false)
            try {
                HealthDns(dns { unexpectedLookup.set(true); emptyList() }).lookup("other.test")
                error("Expected occupied DNS slot refusal")
            } catch (_: IOException) { check(!unexpectedLookup.get()) }
        } finally {
            release.countDown()
            resolver.cancel()
            caller.shutdownNow()
            check(exited.await(2, TimeUnit.SECONDS))
        }
    }
}
