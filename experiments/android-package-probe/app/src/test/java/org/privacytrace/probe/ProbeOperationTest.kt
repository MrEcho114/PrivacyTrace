package org.privacytrace.probe

import org.junit.Assert.*
import org.junit.Test

class ProbeOperationTest {
    @Test fun busyUntilCancelledWorkerDrains() {
        val gate = ProbeOperationGate()
        val old = gate.begin()!!
        assertNull(gate.begin())
        gate.cancel()
        assertTrue(old.cancelled.get())
        assertNull(gate.begin())
        assertFalse(gate.complete(old))
        assertNotNull(gate.begin())
    }

    @Test fun cancelledOperationCannotClearOrCancelNewOperation() {
        val gate = ProbeOperationGate()
        val old = gate.begin()!!
        gate.cancel()
        assertFalse(gate.complete(old))
        val next = gate.begin()!!
        assertFalse(old === next)
        assertTrue(old.cancelled.get())
        assertFalse(gate.complete(old))
        assertNull(gate.begin())
        assertFalse(next.cancelled.get())
        assertTrue(gate.complete(next))
        assertFalse(gate.complete(next))
    }

    @Test fun resultQueuedBeforePauseIsRejectedEvenAfterResume() {
        val gate = ProbeOperationGate()
        val old = gate.begin()!!
        gate.pause()
        assertNull(gate.begin())
        gate.resume()
        assertFalse(gate.complete(old))
        assertTrue(gate.complete(gate.begin()!!))
    }

    @Test fun destroyPermanentlyRejectsResultsAndNewWork() {
        val gate = ProbeOperationGate()
        val old = gate.begin()!!
        gate.destroy()
        gate.resume()
        assertTrue(old.cancelled.get())
        assertFalse(gate.complete(old))
        assertNull(gate.begin())
    }

    @Test fun recreatedActivityUsesANewGateAndRejectsOldCompletion() {
        val oldGate = ProbeOperationGate()
        val old = oldGate.begin()!!
        oldGate.destroy()
        val newGate = ProbeOperationGate()
        val next = newGate.begin()!!
        assertFalse(newGate.complete(old))
        assertNull(newGate.begin())
        assertTrue(old.cancelled.get())
        assertTrue(newGate.complete(next))
    }
}
