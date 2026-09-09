"""Fake executables for client tests, runnable on every OS.

A `#!/bin/sh` script is not executable on Windows — `CreateProcess` answers
`[WinError 193] %1 is not a valid Win32 application` — so three client tests
were POSIX-only and the Windows runner reported them as framework failures.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path


def write_exe(path: Path, *, posix: str, windows: str) -> Path:
    """Write a runnable script at `path`; on Windows it becomes `<path>.cmd`."""
    if sys.platform == "win32":
        path = path.with_suffix(".cmd")
        path.write_text(windows, encoding="utf-8")
        return path
    path.write_text(posix, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def dump_env(path: Path) -> Path:
    """Fake client that writes its own environment to `env.txt` in its cwd."""
    return write_exe(path,
                     posix='#!/bin/sh\nenv > "$PWD/env.txt"\n',
                     windows='@set > "%CD%\\env.txt"\r\n')


def sleeps(path: Path, seconds: int) -> Path:
    """Fake client that ignores its arguments and blocks for `seconds`."""
    return write_exe(path,
                     posix=f"#!/bin/sh\nsleep {seconds}\n",
                     windows=f"@ping -n {seconds + 1} 127.0.0.1 >nul\r\n")
