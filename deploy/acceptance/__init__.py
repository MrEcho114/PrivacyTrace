"""Repeatable acceptance evidence collection for Issue #81 (R2/R4/R5/R6).

The package only collects and judges evidence. It never starts, seeds or tears
down the verified topology: collectors observe an already-running deployment,
or record an explicit SKIP with the precondition that was missing.

Status vocabulary is fixed and deliberately separate:

* ``PASS`` - the collector observed the asserted outcome.
* ``FAIL`` - the collector ran and the asserted outcome did not hold.
* ``SKIP`` - the collector could not run (missing topology, command or input).
* ``NOT_TESTED`` - the scale or condition was explicitly out of scope.

``SKIP`` and ``NOT_TESTED`` are counted separately and never promoted to PASS.
"""
