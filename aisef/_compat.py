"""Cross-platform helpers for Unix-only syscalls (fcntl, process groups)."""

from __future__ import annotations

import os
import sys

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
