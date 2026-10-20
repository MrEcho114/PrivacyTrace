package org.privacytrace.probe

import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Parameterized::class)
class HealthDnsTest(private val case: HealthDnsCase) {
    companion object {
        @JvmStatic @Parameterized.Parameters(name = "{0}")
        fun cases(): Collection<Array<Any>> = HealthDnsCase.values().map { arrayOf<Any>(it) }
    }
    @Test fun `DNS caller cancellation and wait remain bounded`() { HealthDnsChecks.run(case) }
}
