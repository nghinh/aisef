"""Fake executables for client tests, runnable on every OS.

A `#!/bin/sh` script is not executable on Windows — `CreateProcess` answers
`[WinError 193] %1 is not a valid Win32 application` — so three client tests
were POSIX-only and the Windows runner reported them as framework failures.
"""

from __future__ import annotations

import shlex
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


def dump_env(path: Path, out: Path) -> Path:
    """Fake client that writes its own environment to `out`.

    An absolute destination, not `$PWD/env.txt`: adapters differ on whether
    they set the child's cwd or pass the directory as a flag, and the fixture
    must not depend on which.
    """
    return write_exe(path,
                     posix=f'#!/bin/sh\nenv > "{out}"\n',
                     windows=f'@set > "{out}"\r\n')


def sleeps(path: Path, seconds: int) -> Path:
    """Fake client that ignores its arguments and blocks for `seconds`."""
    return write_exe(path,
                     posix=f"#!/bin/sh\nsleep {seconds}\n",
                     windows=f"@ping -n {seconds + 1} 127.0.0.1 >nul\r\n")


def emits_then_sleeps(path: Path, *, prefix_lines: list[str], sleep_seconds: int) -> Path:
    """Fake client that emits each `prefix_lines` JSONL line, then blocks.

    Used to verify partial-stream capture: a harness that only reads stdout
    *after* `kill()` would lose the lines written before `sleep`; one that
    drains concurrently keeps them.  Lines are written to stdout with
    explicit `flush` so the subprocess pipe sees them immediately on POSIX
    (default is line-buffered for terminals, block-buffered for pipes —
    `stdbuf` is not available everywhere, hence the explicit write).
    """
    posix_body = "#!/bin/sh\n"
    for line in prefix_lines:
        # `printf %s\\n` prints one logical line; no interpolation.
        posix_body += f"printf '%s\\n' {shlex.quote(line)}\n"
    posix_body += f"sleep {sleep_seconds}\n"
    return write_exe(path, posix=posix_body,
                     windows="@echo only testable on POSIX at the moment\r\n")
