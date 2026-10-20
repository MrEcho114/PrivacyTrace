package org.privacytrace.probe

import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Parameterized::class)
class HealthDocumentTest(private val case: HealthDocumentCase) {
    companion object {
        @JvmStatic @Parameterized.Parameters(name = "{0}")
        fun cases(): Collection<Array<Any>> = HealthDocumentCase.values().map { arrayOf<Any>(it) }
    }
    @Test fun `strict health document grammar and fixed refusal`() { HealthDocumentChecks.run(case) }
}
