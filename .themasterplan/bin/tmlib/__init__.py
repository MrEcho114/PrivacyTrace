"""/TheMasterplan executor package: deterministic file operations for TheMasterplan adoption.

This package implements the deterministic executor layer of the /TheMasterplan unified
entrypoint. The Skill layer understands and orchestrates; this layer performs
inspect / plan-adopt / apply-adopt / verify with machine-checkable results.

Only the Python standard library is used.
"""

from .util import SCHEMA_VERSION, TheMasterplanError, PathSafetyError

__all__ = ["SCHEMA_VERSION", "TheMasterplanError", "PathSafetyError"]
