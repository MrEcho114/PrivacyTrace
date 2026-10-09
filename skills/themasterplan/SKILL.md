---
name: themasterplan
description: Apply TheMasterplan delivery governance in repositories that have adopted it, or when the user invokes /TheMasterplan.
---

# TheMasterplan

Read the repository root `AGENTS.md`.

Use its Context Router and load only guidance relevant to the current task.
Do not preload unrelated Core, release, update, VCS, adoption, or compatibility
documents.

If another delivery workflow already owns the task, follow the repository's
abstention rule and stop TheMasterplan rather than competing for ownership.

Within the authorized scope, continue until the requested result is complete,
relevant validation passes, failures caused by the change are fixed and
revalidated, and the final diff has been reviewed — or until a genuine human
decision boundary is reached.

Mechanical contracts belong to their files and validators. For example, use the
repository Pull Request template and CI validator instead of reproducing their
field lists here.
