"""The attempt owns its process tree (F5 / INV-L.1, INV-L.2).

Two layers, both stdlib-only:

* ``children_of`` / ``reap_new_children`` — every session (a real client's child process, or an in-process fake that
  spawned something) runs between a snapshot of THIS process's children and a reap of the ones that appeared:
  terminate, wait, kill, VERIFY. What a session leaves behind never outlives the session (FM-C-11).
* ``reap_group`` — a real client's session runs in its own process group (POSIX) or job object (Windows); on EVERY
  exit of the stream, members that outlived the leader (a dev server, a `git gc`) are terminated and verified dead
  before anything removes the workspace (D-024).

Every reap is returned as a list of pids so the caller records it as evidence, never as a silent side effect.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

GRACE_SECONDS = 2.0


def pid_alive(pid: int) -> bool:
    from ..control.state import pid_alive as _alive
    return _alive(pid)


def children_of(pid: int | None = None) -> set[int]:
    """Direct children of ``pid`` (default: this process) — read-only, never a guess."""
    pid = pid or os.getpid()
    if sys.platform == "win32":
        return _children_win32(pid)
    if os.path.isdir("/proc"):                                  # Linux: no subprocess, read the ppid field of each stat
        kids: set[int] = set()
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as fh:
                    stat = fh.read()
                ppid = int(stat[stat.rindex(")") + 2:].split()[1])
            except (OSError, ValueError, IndexError):
                continue
            if ppid == pid:
                kids.add(int(name))
        return kids
    try:
        out = subprocess.run(["ps", "-eo", "pid=,ppid="], capture_output=True, text=True, encoding="utf-8", timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    kids: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) == pid and parts[0].isdigit():
            kids.add(int(parts[0]))
    return kids


def _children_win32(root: int) -> set[int]:
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if snap == ctypes.c_void_p(-1).value or not snap:
        return set()
    kids: set[int] = set()
    try:
        e = PROCESSENTRY32(); e.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if int(e.th32ParentProcessID) == root:
                kids.add(int(e.th32ProcessID))
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return kids


def _terminate(pid: int, hard: bool) -> None:
    if sys.platform == "win32":
        subprocess.call(["taskkill", "/F" if hard else "", "/T", "/PID", str(pid)] if hard else ["taskkill", "/T", "/PID", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    import signal
    try:
        os.kill(pid, signal.SIGKILL if hard else signal.SIGTERM)
    except OSError:
        pass


def reap(pids: set[int] | list[int], *, grace: float = GRACE_SECONDS) -> list[int]:
    """Terminate, wait up to ``grace``, kill, VERIFY. Returns the pids that were alive and are now dead."""
    live = [p for p in pids if pid_alive(p)]
    if not live:
        return []
    for p in live:
        _terminate(p, hard=False)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and any(pid_alive(p) for p in live):
        time.sleep(0.05)
    for p in live:
        if pid_alive(p):
            _terminate(p, hard=True)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and any(pid_alive(p) for p in live):
        time.sleep(0.05)
    for p in live:
        try:
            os.waitpid(p, os.WNOHANG)          # reap a zombie child of ours; harmless for a non-child
        except (ChildProcessError, OSError):
            pass
    return [p for p in live if not pid_alive(p)]


def reap_new_children(before: set[int]) -> list[int]:
    """Reap every child of this process that appeared since ``before`` (the session's leftovers)."""
    return reap(children_of() - set(before))


def survivors(before: set[int]) -> list[int]:
    return sorted(p for p in (children_of() - set(before)) if pid_alive(p))


def reap_group(proc: subprocess.Popen) -> list[int]:
    """After the session's leader exited: members of its process group that outlived it (POSIX). Windows sessions are
    bound to a job object whose close kills them (`win_job`); here it returns []."""
    if sys.platform == "win32":
        return []
    import signal
    pgid = proc.pid
    try:
        os.killpg(pgid, 0)
    except OSError:
        return []                              # nothing left in the group
    members = _group_members(pgid)
    try:
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        return members
    deadline = time.monotonic() + GRACE_SECONDS
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except OSError:
            return members
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass
    return members


def _group_members(pgid: int) -> list[int]:
    try:
        out = subprocess.run(["ps", "-eo", "pid=,pgid="], capture_output=True, text=True, encoding="utf-8", timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    out_pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) == pgid and parts[0].isdigit():
            out_pids.append(int(parts[0]))
    return out_pids


class win_job:
    """Windows: bind a just-spawned session to a job object that kills every descendant when closed."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self.handle = None
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                              "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

            class EXTENDED(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            job = k32.CreateJobObjectW(None, None)
            if not job:
                return
            info = EXTENDED(); info.BasicLimitInformation.LimitFlags = 0x2000     # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                k32.CloseHandle(job); return
            handle = getattr(proc, "_handle", None)
            if handle is None or not k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(handle))):
                k32.CloseHandle(job); return
            self.handle = job
        except Exception:  # noqa: BLE001 — no job object: the taskkill tree fallback stays
            self.handle = None

    def close(self) -> None:
        if self.handle is not None and sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.CloseHandle(self.handle)  # type: ignore[attr-defined]
            self.handle = None
