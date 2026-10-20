package org.privacytrace.probe

import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Parameterized::class)
class HttpsHealthCallTest(private val case: HealthTlsCase) {
    companion object {
        @JvmStatic @Parameterized.Parameters(name = "{0}")
        fun cases(): Collection<Array<Any>> = HealthTlsCase.values().map { arrayOf<Any>(it) }
    }
    @Test fun `bounded native HTTPS behavior over actual TLS sockets`() { HealthTlsChecks.run(case) }
}
