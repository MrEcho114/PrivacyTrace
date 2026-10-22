"""WSL distribution selection for hosts that reach Docker through wsl.exe.

Windows installs are not guaranteed to name their distribution ``Ubuntu-24.04``
(the Microsoft Store alias, a pinned version, Debian or a purpose-built runner
distribution are all valid). The distribution is host configuration, so read it
once here and let every wsl.exe call use the same name.
"""

import os

DEFAULT_WSL_DISTRO = "Ubuntu-24.04"


def wsl_distro():
    """Distribution used for wsl.exe calls; override with PRIVACYTRACE_WSL_DISTRO."""
    return os.environ.get("PRIVACYTRACE_WSL_DISTRO") or DEFAULT_WSL_DISTRO
