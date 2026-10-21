"""Explicit capacity refusals shared by intake, admission and disk budgets.

A capacity boundary is not an input rejection. Callers (the HTTP seam, the
acceptance drills and the operator) must be able to tell a spent budget from a
malformed request, so every refusal carries a stable machine code and, when a
retry can succeed on its own, a retry hint.
"""


class CapacityRefused(ValueError):
    """A documented admission, queue or disk budget is spent."""

    def __init__(self, code, message, *, retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
