"""Translate owned local paths for the local Docker daemon used by isolation."""

import os
import subprocess
from pathlib import Path


def daemon_path(path):
    path = Path(path).absolute()
    if os.name == "nt":
        return subprocess.check_output(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-a", str(path)],
            text=True,
        ).strip()
    return str(path)
