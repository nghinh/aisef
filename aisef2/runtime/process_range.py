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
  never signals again. **One release at a time** (single flight): the ladder, the EXIT write, the reap and the pipe
  close of one range are never run by two threads; a second caller waits for the first and is given its outcome.
* `descendants` walks a process table for *reporting* only: a visited set, stale parent edges dropped (a parent
  created after its child), bounded by the table. Nothing it returns is ever signalled (WIN-PID-1, WIN-PID-2).
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import re
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


class ProcessTableError(Exception):
    """`ps` printed a line that is not a process row. The table is not returned: a row dropped is a process the table
    cannot see (a member, a survivor) and a row made up is one that is not there. Not a `Residual` (it says nothing
    about what is alive) and not a `RangeError` (callers read that as "the tool could not start" and go on): it
    propagates, as a failed `ps` (`CalledProcessError`) always did. The message names the line, cut to 80 characters."""


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
            # bytes, decoded with replacement: a process's name is its own (`prctl(PR_SET_NAME)`), and one that is not
            # UTF-8 made `read_text()` raise UnicodeDecodeError — not the OSError skipped below — for the whole host
            stat = pathlib.Path(entry.path, "stat").read_bytes().decode("utf-8", "replace")
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
    r = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,stat=,command="], capture_output=True, check=True)
    out = {}
    # A row ends at "\n" and nowhere else. `ps` escapes a newline inside a command (`\012`) but prints U+2028, U+2029
    # and the like raw (in a UTF-8 locale), so `str.splitlines()` — and text mode, which also turns "\r" into "\n" —
    # cut a row inside its command: the tail was dropped (a survivor named after the cut was not found), or raised
    # (`int('alpha')`), or, when it looked like a row, became one (a process that is not there).
    for line in r.stdout.decode("utf-8", "replace").split("\n"):
        if not line.strip(" "):
            continue  # the end of the output (it ends with "\n"), or a blank line: no process
        m = re.fullmatch(r" *([0-9]+) +([0-9]+) +([0-9]+) +([^ ]+)(?: +(.*))?", line)  # pid ppid pgid stat [command]
        if m is None:
            raise ProcessTableError(f"ps printed a line that is not a process row: {line[:80]!r}")
        if m[4].startswith("Z"):
            continue
        out[int(m[1])] = Proc(int(m[1]), int(m[2]), int(m[3]), None, m[5] or "")
    return out


def process_table() -> dict[int, Proc]:
    """The live processes (POSIX). Linux: /proc; elsewhere: ps."""
    return _linux_table() if LINUX else _ps_table()


# Win32 liveness-probe constants (FINDING-WIN-OSKILL-001 H2, + the gate-3 false-gone fix 2026-11-06).
_WIN_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000   # OpenProcess access: query only, NO PROCESS_TERMINATE
_WIN_ERROR_INVALID_PARAMETER = 87                 # OpenProcess's "no such process id": the ONLY reliable "gone"
_WIN_STILL_ACTIVE = 259                           # GetExitCodeProcess: the process has not terminated


def _win_liveness(handle_opened: bool, last_error: int, exit_code_read: bool, exit_code: int) -> bool:
    """Pure decision for the Windows liveness probe (the live probe below feeds it the real ctypes results),
    so every branch is provable off-Windows. Returns True=alive / False=gone. GONE is concluded ONLY from
    reliable evidence of non-existence: OpenProcess failing with ERROR_INVALID_PARAMETER (87 — no such pid),
    or a handle that opened and reported a real exit code (the process terminated). EVERY other OpenProcess
    failure — ERROR_ACCESS_DENIED (5, exists but not ours), resource exhaustion (ERROR_NOT_ENOUGH_MEMORY 8 /
    ERROR_NO_SYSTEM_RESOURCES 1450), or any other/unknown error — is ambiguous and reads ALIVE (fail closed:
    a false 'gone' would let a live developer escapee pass as gone and the session keep its outcome). The
    STILL_ACTIVE=259 case where a process exited with code 259 also reads ALIVE — the safe direction.
    DOCUMENTED LIMIT: Windows gives no way to tell a true exit from an unreadable probe except error 87 and a
    read exit code, so an ambiguous failure is NEVER inferred as GONE; the session is refused rather than
    guessed (gate-3 owner directive: fail closed, do not infer)."""
    if not handle_opened:
        return last_error != _WIN_ERROR_INVALID_PARAMETER
    if not exit_code_read:
        return True                     # handle opened but exit code unreadable: cannot prove gone -> alive
    return exit_code == _WIN_STILL_ACTIVE


def pid_alive(pid: int) -> bool:
    """Whether a process with this id exists on this host, read-only — it never signals and never terminates. The
    probe `_is_gone` uses in place of a bare `os.kill(pid, 0)`, which on Windows is destructive (signal 0 is
    CTRL_C_EVENT, routed to TerminateProcess on CPython <= 3.12; FINDING-WIN-OSKILL-001 H2). POSIX: signal 0 — ESRCH
    means gone, EPERM (or any other OSError) means it exists and is not ours. Windows: OpenProcess for limited query +
    GetExitCodeProcess, decided by `_win_liveness` — only ERROR_INVALID_PARAMETER (no such pid) or a read exit code
    is gone; ACCESS_DENIED, resource exhaustion and every other failure read ALIVE. Ambiguity always reads as ALIVE,
    never dead: a wrong 'dead' is the costlier mistake here (it would let a live developer process pass as gone and the
    session keep its outcome)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype, k.OpenProcess.argtypes = wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.GetExitCodeProcess.restype = wintypes.BOOL
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.restype, k.CloseHandle.argtypes = wintypes.BOOL, [wintypes.HANDLE]
        h = k.OpenProcess(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return _win_liveness(False, ctypes.get_last_error(), False, 0)
        try:
            code = wintypes.DWORD()
            got = bool(k.GetExitCodeProcess(h, ctypes.byref(code)))
            return _win_liveness(True, 0, got, code.value)
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True   # EPERM or any other OSError: it exists / cannot prove gone -> alive
    return True       # it answered: alive


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
        except (ProcessLookupError, PermissionError):
            # ESRCH: the group is already empty (the anchor, unreaped, still pins its id). EPERM: macOS answers it
            # when no member could be signalled — every one already exiting or a zombie (XNU killpg1: nfound == 0);
            # a member of another user cannot be in this session's group. Either way nothing was there to signal,
            # and what the range holds is still measured by wait_empty, never assumed from this answer.
            pass

    def abort(self, anchor: subprocess.Popen) -> None:
        if anchor.poll() is None:
            try:
                os.killpg(anchor.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                # the anchor ended between poll() and the signal (ESRCH, or EPERM where macOS answers it for a group
                # of zombies): nothing is left to kill, and the failure that led here must not be replaced by this one
                # — `_abort` goes on to reap the anchor and close the pipes
                pass

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

class _Flight:
    """One release in progress (single flight): the thread leading it, whether it is past the ladder, what it saw leave
    the range, and — when it ends in a `Residual` — that outcome, which every caller that waited for it is given."""

    __slots__ = ("thread", "disposing", "escaped", "done", "outcome")

    def __init__(self) -> None:
        self.thread = threading.get_ident()
        self.disposing = False   # True once the range is measured empty: the anchor may be reaped, nothing signals
        self.escaped: dict[int, Proc] = {}
        self.done = False        # set by the leader, last; read by the callers that wait
        self.outcome: Residual | None = None


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
        self._mx = threading.RLock()          # guards `_flight` only; re-entrant, never held while anything waits
        self._flight: _Flight | None = None   # the release in progress (or the last one, done)

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
    def output(self):
        """The stream carrying the target's stdout and stderr, when the range was started with output=PIPE."""
        return None if self._anchor is None else self._anchor.stderr

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

    def left_the_range(self) -> list[Proc]:
        """What the last release saw leave the range (`_Flight.escaped`), as recorded — readable after the reap, when
        `escaped()` can no longer measure. A RangeEscaped names these; a caller re-checks them against the table to tell
        a process caught mid-exit at release (gone within a grace) from one that stays alive (PL-7). Nothing is signalled."""
        return list((self._flight.escaped if self._flight is not None else {}).values())

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
        RangeNotEmpty (RESIDUAL) when it does not empty, RangeEscaped when processes that left it are alive.

        One release at a time. A caller that arrives while another thread is releasing waits for it and is given its
        outcome — the same RangeNotEmpty or RangeEscaped, so a leak is not silent for either — and runs no ladder, EXIT
        write or pipe close of its own. A call after a release has ended is what it always was: a no-op once the anchor
        is reaped, a new ladder after RangeNotEmpty. A call from the thread that is already releasing (a signal
        handler) stops the range when the frame below is still in the ladder and returns at once past it: that frame
        disposes. A caller waits exactly as long as the release it waits for — by polling, as `wait_empty` does, so
        that nothing a re-entering handler could meet is held while it waits."""
        flight = outcome = None
        try:
            while flight is None:
                with self._mx:
                    current = self._flight
                    if current is None or current.done:
                        if self._anchor is None or self._reaped:
                            return
                        flight = self._flight = _Flight()
                if flight is None:   # a release is in flight
                    if current.thread == threading.get_ident():
                        if not current.disposing:
                            self._ladder(current)
                        return
                    while not current.done:
                        time.sleep(POLL_S)
                    if current.outcome is not None:
                        raise type(current.outcome)(*current.outcome.args) from current.outcome
            self._release(flight)
        except Residual as e:
            outcome = e   # RangeNotEmpty / RangeEscaped: raised below, once `done` is set
            if flight is not None:
                flight.outcome = e
        finally:
            if flight is not None:
                flight.done = True
        if outcome is not None:
            raise outcome

    def _ladder(self, flight: _Flight) -> None:
        """Stop the range, graceful-first, until it is measured empty; RangeNotEmpty when it does not empty."""
        flight.escaped.update({p.pid: p for p in self.escaped()})  # seen while their parents are alive
        empty = self.wait_empty(0.0) and self.wait(0.0) is not None
        for stage, sig, grace in self._os.stages:
            if empty:
                break
            self._signal(stage, sig)
            empty = self.wait_empty(self._wait if grace is None else self._grace[grace])
        if not empty:
            raise RangeNotEmpty(f"{self.name}: not empty after {[s['stage'] for s in self.ledger]}: "
                                f"{[(p.pid, p.command) for p in self.members()]}")

    def _release(self, flight: _Flight) -> None:
        """The ladder, then the disposal: EXIT to the anchor, the reap, the pipes and the backend closed, and the check
        that nothing which left the range is alive. RangeEscaped when something is."""
        self._ladder(flight)
        flight.disposing = True  # measured empty: from here the anchor may be reaped, and nothing is signalled
        flight.escaped.update({p.pid: p for p in self.escaped()})  # Linux: orphaned escapees re-parent to the anchor
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
        live = process_table() if flight.escaped else {}
        still = sorted(pid for pid in flight.escaped if pid in live)
        if still:
            raise RangeEscaped(f"{self.name}: processes left the range and are alive: "
                               f"{[(pid, live[pid].command) for pid in still]}")
