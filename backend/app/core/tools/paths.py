from __future__ import annotations

import os
from pathlib import Path


def safe_resolve(workspace_dir: str, path: str) -> Path | None:
    """Resolve ``path`` against ``workspace_dir``, rejecting any escape.

    Returns the absolute ``Path`` if it stays inside the workspace, otherwise
    ``None``. Absolute ``path`` values are treated as relative to the workspace
    and still checked (so ``/etc/passwd`` is rejected), guarding against both
    ``..`` traversal and absolute-path injection.
    """
    base = os.path.abspath(workspace_dir)
    target = os.path.abspath(os.path.join(base, path))
    if target != base and not target.startswith(base + os.sep):
        return None
    return Path(target)
