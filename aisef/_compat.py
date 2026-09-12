"""Cross-platform helpers for Unix-only syscalls (fcntl, process groups)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # chú thích kiểu dùng `subprocess`; thân hàm tự import khi chạy
    import subprocess

import os
import sys
import time

_WIN = sys.platform == "win32"

# ── file locking ──────────────────────────────────────────────

if _WIN:
    import msvcrt

    def flock_ex_nb(fd: int) -> None:
        """Non-blocking exclusive lock (Windows).

        msvcrt.locking locks a byte range at the current position.  We
        ensure the file has at least 1 byte, seek to 0, and lock that
        byte.  Raises BlockingIOError when the lock is held.
        """
        # Ensure the file has at least 1 byte so locking has something to lock.
        pos = os.lseek(fd, 0, os.SEEK_END)
        if pos == 0:
            os.write(fd, b"\0")
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as e:
            raise BlockingIOError(str(e)) from e

    def flock_un(fd: int) -> None:
        """Unlock (Windows)."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def flock_ex_nb(fd: int) -> None:  # type: ignore[misc]
        """Non-blocking exclusive lock (Unix)."""
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def flock_un(fd: int) -> None:  # type: ignore[misc]
        """Unlock (Unix)."""
        fcntl.flock(fd, fcntl.LOCK_UN)


# ── process termination ──────────────────────────────────────

if _WIN:
    def kill_process_tree(proc: "subprocess.Popen[bytes]") -> None:
        """Kill a process and its children (Windows)."""
        import subprocess
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
else:
    def kill_process_tree(proc: "subprocess.Popen[bytes]") -> None:  # type: ignore[misc]
        """Kill process group (Unix)."""
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except (ProcessLookupError, ChildProcessError):
            pass
        except Exception:  # noqa: BLE001
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, ChildProcessError):
                pass


def subprocess_new_session_kwargs() -> dict:
    """Return kwargs for subprocess.Popen to start in a new session/group."""
    if _WIN:
        import subprocess
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}

# ── lock file descriptors ────────────────────────────────────

#: Flag that keeps a lock descriptor out of child processes.  POSIX spells it
#: ``O_CLOEXEC``; Windows has no such flag on ``os.open`` and spells the same
#: intent ``O_NOINHERIT``.  Reading it off ``os`` by name rather than importing
#: the POSIX one keeps a single call site working on both — the phase-2 lease
#: and budget lock used ``os.O_CLOEXEC`` directly and raised ``AttributeError``
#: on every Windows run (CI, 2026-09-12).
def _no_inherit_flag(osmod=os) -> int:
    """The flag this OS uses; 0 when it offers neither (then the fd is
    simply inheritable — degraded, not broken)."""
    return getattr(osmod, "O_CLOEXEC", 0) or getattr(osmod, "O_NOINHERIT", 0)


_NO_INHERIT = _no_inherit_flag()


def open_lock_fd(path, mode: int = 0o600) -> int:
    """Open (creating if needed) a file to hold an advisory lock, portably."""
    return os.open(str(path), os.O_CREAT | os.O_RDWR | _NO_INHERIT, mode)


# ── atomic replace ───────────────────────────────────────────

def atomic_replace(src, dst, *, attempts: int = 25, delay: float = 0.02) -> None:
    """``os.replace`` that survives Windows sharing semantics.

    On POSIX a rename over an open file always succeeds — the reader keeps the
    old inode.  On Windows the same call raises ``PermissionError`` (WinError
    5) while **any** handle to the destination is open, so a reader that
    happens to overlap a writer turns a correct atomic write into a crash
    (measured on CI 2026-09-12: concurrent writers on the memory store).

    The retry window is short and bounded: a genuine permission problem still
    raises, just half a second later, and the caller sees the real exception
    rather than a swallowed one.
    """
    for remaining in range(attempts - 1, -1, -1):
        try:
            os.replace(str(src), str(dst))
            return
        except PermissionError:
            if not _WIN or remaining == 0:
                raise
            time.sleep(delay)
