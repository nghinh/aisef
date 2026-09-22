"""RFC §17.1 — measured process-range emptiness (WP-4.2; P4-LIFETIME-SEMANTICS.md §3).

**Ownership is the operating system's, never PID equality or ancestry** (the frozen WP-4.2 property, V1-PF-001).

* POSIX: the range is the session and process group of its anchor (`range_anchor.py`), the controller's own child,
  which is not reaped until the range is disposed — so the group id cannot be reused while a signal can be sent to it.
  Members are the live processes of that group; a descendant that leaves it (`setsid`) is not a member and is reported
  as escaped (Linux: the anchor is a child subreaper, so an orphaned escapee re-parents to it).
* Windows: a Job object with KILL_ON_JOB_CLOSE and no breakaway; the anchor is assigned to it before it starts the
  target, so every descendant is a member. Members are the job's process list.
* **Emptiness is measured** from the process table or the job, never from the direct child's exit status.
* **`release`** is the graceful-first ladder: cooperative (SIGINT) -> grace -> SIGTERM -> grace -> SIGKILL -> wait
  (Windows: TerminateJobObject -> wait). Every signal is sent while the anchor is unreaped and is recorded in `ledger`.
  A range that does not empty raises `RangeNotEmpty` (the resource is RESIDUAL); after the anchor is reaped the range
  never signals again.
* `descendants` walks a process table for *reporting* only: a visited set, stale parent edges dropped (a parent
  created after its child), bounded by the table. Nothing it returns is ever signalled (WIN-PID-1, WIN-PID-2).
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Mapping, Sequence

from aisef2.journal.format2 import ResourceKind
from aisef2.runtime.story_scope import Residual

ANCHOR = pathlib.Path(__file__).with_name("range_anchor.py")
POSIX = os.name == "posix"
LINUX = sys.platform.startswith("linux")
GRACE_S = (2.0, 2.0)  # after the cooperative signal, after SIGTERM
JOB_EXIT_CODE = 0xAE5F  # the exit status TerminateJobObject gives every member: a controller's stop, recognisable
POLL_S = 0.02


class RangeError(Exception):
    """The range could not be started or used."""


class RangeNotEmpty(Residual):
    """The range did not empty: its members are named, and nothing that depends on it may be released."""


class RangeEscaped(Residual):
    """The range emptied, but processes that left it (`setsid`) are alive: named, never signalled — they are not the
    range's — and, since they could still write, nothing that depends on the range may be released either."""


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    group: int | None      # POSIX process group; None where the table has none
    created: float | None  # a start time comparable within one table; None where unknown
    command: str = ""


# --------------------------------------------------------------------------------------- process tables

def _linux_table() -> dict[int, Proc]:
    out = {}
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            stat = pathlib.Path(entry.path, "stat").read_text()
            cmd = pathlib.Path(entry.path, "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue  # it exited while the table was read
        comm_end = stat.rindex(")")
        f = stat[comm_end + 2:].split()
        if f[0] in ("Z", "X"):
            continue  # a zombie or a dead task holds no resource and cannot write
        out[int(entry.name)] = Proc(int(entry.name), int(f[1]), int(f[2]), float(f[19]), cmd.strip())
    return out


def _ps_table() -> dict[int, Proc]:
    r = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,stat=,command="], capture_output=True, encoding="utf-8",
                       errors="replace", check=True)
    out = {}
    for line in r.stdout.splitlines():
        f = line.split(None, 4)
        if len(f) < 4 or f[3].startswith("Z"):
            continue
        out[int(f[0])] = Proc(int(f[0]), int(f[1]), int(f[2]), None, f[4] if len(f) > 4 else "")
    return out


def process_table() -> dict[int, Proc]:
    """The live processes (POSIX). Linux: /proc; elsewhere: ps."""
    return _linux_table() if LINUX else _ps_table()


def descendants(table: Mapping[int, Proc], root: int) -> list[int]:
    """Processes whose parent chain reaches `root`, for reporting only. Terminates on any table (a visited set; each
    pid once), and drops a parent edge when the parent was created after the child — Windows and POSIX keep a dead
    parent's pid in the child, and that pid may since belong to an unrelated process (V1-PF-001)."""
    children: dict[int, list[int]] = {}
    for p in table.values():
        parent = table.get(p.ppid)
        if p.ppid == p.pid or parent is None:
            continue
        if p.created is not None and parent.created is not None and parent.created > p.created:
            continue  # a stale edge: that "parent" is younger than its child, so it is not the parent
        children.setdefault(p.ppid, []).append(p.pid)
    out, seen, todo = [], {root}, list(children.get(root, ()))
    while todo:
        pid = todo.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        todo.extend(children.get(pid, ()))
    return sorted(out)


def targets(table: Mapping[int, Proc], members: Sequence[int]) -> list[int]:
    """What a disposal may signal: the members the ownership mechanism reports, and nothing found by ancestry."""
    return sorted(pid for pid in members if pid in table)


# --------------------------------------------------------------------------------------- OS backends

class _Posix:
    """POSIX: the session and process group of the anchor, which the controller does not reap until disposal."""

    def __init__(self) -> None:
        self.group: int | None = None
        # built here, not in the class body: Windows has no SIGKILL, and this module is imported there too
        self.stages = (("cooperative", signal.SIGINT, 0), ("terminate", signal.SIGTERM, 1),
                       ("kill", signal.SIGKILL, None))

    def popen_kwargs(self) -> dict:
        return {"start_new_session": True}

    def adopt(self, pid: int) -> None:
        self.group = pid  # start_new_session: the anchor leads its own session and group

    def members(self, anchor: int) -> list[Proc]:
        return sorted((p for p in process_table().values() if p.group == self.group and p.pid != anchor),
                      key=lambda p: p.pid)

    def escaped(self, anchor: int) -> list[Proc]:
        table = process_table()
        inside = {p.pid for p in table.values() if p.group == self.group} | {anchor}
        return sorted((p for p in table.values() if p.group != self.group and p.ppid in inside), key=lambda p: p.pid)

    def signal(self, sig) -> None:
        try:
            os.killpg(self.group, sig)
        except ProcessLookupError:
            pass  # the group is already empty (the anchor, unreaped, still pins its id)

    def abort(self, anchor: subprocess.Popen) -> None:
        if anchor.poll() is None:
            os.killpg(anchor.pid, signal.SIGKILL)

    def close(self) -> None:
        pass

    @staticmethod
    def controller_stopped(returncode: int | None, ledger: Sequence[Mapping]) -> bool:
        return False  # a POSIX stop is a signal exit, a negative status named by its signal


class _Job:
    """Windows: a Job object with KILL_ON_JOB_CLOSE and no breakaway. The OS adapter, exercised on Windows CI."""

    stages = (("terminate_job", "TerminateJobObject", None),)
    JobObjectBasicAccountingInformation, JobObjectBasicProcessIdList, JobObjectExtendedLimitInformation = 1, 3, 9
    KILL_ON_JOB_CLOSE = 0x2000
    PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes
        self._c, self._w = ctypes, wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype, k.CreateJobObjectW.argtypes = wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR]
        k.SetInformationJobObject.restype = wintypes.BOOL
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.AssignProcessToJobObject.restype = wintypes.BOOL
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.QueryInformationJobObject.restype = wintypes.BOOL
        k.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                ctypes.POINTER(wintypes.DWORD)]
        k.TerminateJobObject.restype, k.TerminateJobObject.argtypes = wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT]
        k.OpenProcess.restype, k.OpenProcess.argtypes = wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.CloseHandle.restype, k.CloseHandle.argtypes = wintypes.BOOL, [wintypes.HANDLE]
        self._k = k

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_ulonglong * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        class PidList(ctypes.Structure):
            _fields_ = [("Assigned", wintypes.DWORD), ("InList", wintypes.DWORD), ("Ids", ctypes.c_size_t * 4096)]

        self._PidList = PidList
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise RangeError(f"CreateJobObject failed: {ctypes.get_last_error()}")
        info = Extended()
        info.BasicLimitInformation.LimitFlags = self.KILL_ON_JOB_CLOSE  # no BREAKAWAY_OK: no member can leave
        if not k.SetInformationJobObject(self.handle, self.JobObjectExtendedLimitInformation, ctypes.byref(info),
                                         ctypes.sizeof(info)):
            raise RangeError(f"SetInformationJobObject failed: {ctypes.get_last_error()}")

    def popen_kwargs(self) -> dict:
        return {}

    @staticmethod
    def controller_stopped(returncode: int | None, ledger: Sequence[Mapping]) -> bool:
        """TerminateJobObject gives every member JOB_EXIT_CODE: with that stop in the ledger, the stop was ours."""
        return returncode == JOB_EXIT_CODE and any(s["signal"] == "TerminateJobObject" for s in ledger)

    def adopt(self, pid: int) -> None:
        # the pid is our own unreaped child's: Popen holds its handle, so the pid cannot be reused meanwhile
        h = self._k.OpenProcess(self.PROCESS_SET_QUOTA | self.PROCESS_TERMINATE, False, pid)
        if not h:
            raise RangeError(f"OpenProcess({pid}) failed: {self._c.get_last_error()}")
        try:
            if not self._k.AssignProcessToJobObject(self.handle, h):
                raise RangeError(f"AssignProcessToJobObject failed: {self._c.get_last_error()}")
        finally:
            self._k.CloseHandle(h)

    def members(self, anchor: int) -> list[Proc]:
        return [Proc(pid, 0, None, None) for pid in self._pids() if pid != anchor]

    def escaped(self, anchor: int) -> list[Proc]:
        return []  # no BREAKAWAY_OK: no member can leave the job

    def signal(self, sig) -> None:
        self.terminate()

    def abort(self, anchor: subprocess.Popen) -> None:
        self.terminate()
        self.close()

    def _pids(self) -> list[int]:
        pids = self._PidList()
        if not self._k.QueryInformationJobObject(self.handle, self.JobObjectBasicProcessIdList,
                                                 self._c.byref(pids), self._c.sizeof(pids), None):
            raise RangeError(f"QueryInformationJobObject failed: {self._c.get_last_error()}")
        return [int(pids.Ids[i]) for i in range(pids.InList)]

    def terminate(self) -> None:
        if not self._k.TerminateJobObject(self.handle, JOB_EXIT_CODE):
            raise RangeError(f"TerminateJobObject failed: {self._c.get_last_error()}")

    def close(self) -> None:
        if self.handle:
            h, self.handle = self.handle, None
            self._k.CloseHandle(h)


BACKEND = _Posix if POSIX else _Job


# --------------------------------------------------------------------------------------- the range

class ProcessRange:
    """A StoryScope resource (PROCESS_RANGE) running `argv` inside an OS-owned range."""

    kind = ResourceKind.PROCESS_RANGE

    def __init__(self, name: str, argv: Sequence[str], *, cwd: str | os.PathLike | None = None,
                 env: Mapping[str, str] | None = None, output=subprocess.DEVNULL,
                 grace_s: tuple[float, float] = GRACE_S, wait_s: float | None = None) -> None:
        self.name, self._argv = name, [str(a) for a in argv]
        self._cwd, self._env, self._output = (str(cwd) if cwd is not None else None), env, output
        self._grace, self._wait = grace_s, wait_s
        self.ledger: list[dict] = []   # every signal the controller sent: {stage, signal, at}
        self._anchor: subprocess.Popen | None = None
        self._os: _Posix | _Job | None = None
        self._lines: queue.Queue = queue.Queue()
        self.target_pid: int | None = None
        self.returncode: int | None = None
        self._reaped = False

    # ---- start
    def start(self) -> "ProcessRange":
        if self._anchor is not None:
            raise RangeError(f"{self.name} is already started")
        self._os = BACKEND()
        self._anchor = subprocess.Popen([sys.executable, "-P", str(ANCHOR)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self._output, encoding="utf-8",
                                        **self._os.popen_kwargs())
        self._pumper = threading.Thread(target=self._pump, daemon=True)
        self._pumper.start()
        try:
            self._os.adopt(self._anchor.pid)
            self._anchor.stdin.write(json.dumps({"argv": self._argv, "cwd": self._cwd,
                                                 "env": dict(self._env) if self._env is not None else None}) + "\nGO\n")
            self._anchor.stdin.flush()
            tag, value = self._line(30.0)
        except BaseException:
            self._abort()
            raise
        if tag != "STARTED":
            self._abort()
            raise RangeError(f"{self.name}: the target did not start ({tag} {value})")
        self.target_pid = int(value)
        return self

    def _pump(self) -> None:
        for line in self._anchor.stdout:
            tag, _, value = line.strip().partition(" ")
            self._lines.put((tag, value))
        self._lines.put(("CLOSED", ""))

    def _line(self, timeout: float | None) -> tuple[str, str]:
        try:
            return self._lines.get(timeout=timeout)
        except queue.Empty:
            return "TIMEOUT", ""

    def _abort(self) -> None:
        """A start that failed: kill whatever exists and reap the anchor."""
        self._os.abort(self._anchor)
        self._anchor.wait()
        self._reaped = True
        self._close_pipes()

    def _close_pipes(self) -> None:
        self._pumper.join(5.0)  # the anchor is reaped: its stdout is at end of file
        for pipe in (self._anchor.stdin, self._anchor.stdout):
            try:
                pipe.close()
            except OSError:
                pass

    # ---- observe
    @property
    def group(self) -> int | None:
        return self._os.group if isinstance(self._os, _Posix) else None

    @property
    def anchor_returncode(self) -> int | None:
        """How the anchor itself ended, once reaped (a signal kills it with its group)."""
        return self._anchor.returncode if self._anchor is not None else None

    def wait(self, timeout: float | None = None) -> int | None:
        """The target's exit status, or None if it is still running after `timeout`. Only the direct child: it says
        nothing about the range (see `members`)."""
        if self.returncode is None:
            deadline = None if timeout is None else time.monotonic() + timeout
            while self.returncode is None:
                tag, value = self._line(None if deadline is None else max(0.0, deadline - time.monotonic()))
                if tag == "EXITED":
                    self.returncode = int(value)
                elif tag in ("TIMEOUT", "CLOSED"):
                    if tag == "CLOSED":
                        self._lines.put((tag, value))
                    return None
        return self.returncode

    def members(self) -> list[Proc]:
        """The live members other than the anchor, measured now."""
        if self._anchor is None or self._reaped:
            return []
        return self._os.members(self._anchor.pid)

    def escaped(self) -> list[Proc]:
        """Processes that left the range (POSIX `setsid`): not members, so never signalled, reported as residuals.
        Seen when their parent is a live member or, on Linux, when they were orphaned and re-parented to the anchor."""
        if self._anchor is None or self._reaped:
            return []
        return self._os.escaped(self._anchor.pid)

    def wait_empty(self, timeout: float | None) -> bool:
        """True as soon as the range is measured empty; False if it is not empty when `timeout` ends (None: wait)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.members():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(POLL_S)
        return True

    # ---- dispose
    def _signal(self, stage: str, sig) -> None:
        if self._reaped:
            raise RangeError(f"{self.name}: the anchor is reaped; the range is never signalled again")
        self.ledger.append({"stage": stage, "signal": getattr(sig, "name", str(sig)), "at": time.monotonic()})
        self._os.signal(sig)

    def release(self) -> None:
        """The graceful-first ladder until the range is measured empty; then the anchor is reaped. Raises
        RangeNotEmpty (RESIDUAL) when it does not empty, RangeEscaped when processes that left it are alive."""
        if self._anchor is None or self._reaped:
            return
        escaped = {p.pid: p for p in self.escaped()}  # seen while their parents are alive
        empty = self.wait_empty(0.0) and self.wait(0.0) is not None
        for stage, sig, grace in self._os.stages:
            if empty:
                break
            self._signal(stage, sig)
            empty = self.wait_empty(self._wait if grace is None else self._grace[grace])
        if not empty:
            raise RangeNotEmpty(f"{self.name}: not empty after {[s['stage'] for s in self.ledger]}: "
                                f"{[(p.pid, p.command) for p in self.members()]}")
        escaped.update({p.pid: p for p in self.escaped()})  # Linux: orphaned escapees re-parent to the anchor
        if self._anchor.poll() is None:
            try:
                self._anchor.stdin.write("EXIT\n")
                self._anchor.stdin.flush()
            except OSError:
                pass  # it is already gone
        self._anchor.wait()
        self._reaped = True
        self._close_pipes()
        self._os.close()
        self.wait(1.0)
        live = process_table() if escaped else {}
        still = sorted(pid for pid in escaped if pid in live)
        if still:
            raise RangeEscaped(f"{self.name}: processes left the range and are alive: "
                               f"{[(pid, live[pid].command) for pid in still]}")
