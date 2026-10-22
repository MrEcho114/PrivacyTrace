"""Translate owned local paths for the local Docker daemon used by isolation."""

import os
import subprocess
from pathlib import Path

from privacytrace.wsl import wsl_distro


def output_user():
    """Let an unprivileged Linux caller write its own bind-mounted output."""
    if os.name != "nt" and os.getuid() != 0:
        return ["--user", f"{os.getuid()}:{os.getgid()}"]
    return []  # Windows mounts use the image's non-root user.


def daemon_path(path):
    path = Path(path).absolute()
    if os.name == "nt":
        return subprocess.check_output(
            ["wsl.exe", "-d", wsl_distro(), "--exec", "wslpath", "-a", str(path)],
            text=True,
        ).strip()
    return str(path)
