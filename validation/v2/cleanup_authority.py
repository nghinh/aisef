"""The mutation runner's only authority to signal a process (P4-FINDING-011; owner decision of 2026-09-23 §2–§4).

Stdlib only. This module imports nothing from `aisef2` — those are the modules under mutation — and nothing from
`mutation.py`. Code under mutation may REPORT any process as a member, an escapee or a stray; a report is never
permission. A process is signalled only once this module has proved, from its own reading of the host's process
table, that it belongs to the boundary the runner established before its worker started:

* ancestry — the parent chain reaches the runner's pid;
* birth — it was created after the boundary was established, so the reused pid of an unrelated process is not it;
* a process group — only through its leader (pid == pgid), proved as above: a group id is a namespace its leader
  created, and only members of the leader's session can join it.

Anything else is RESIDUAL_OWNERSHIP_UNKNOWN: it is not signalled, and the caller fails its target. A leaked test
process is preferable to signalling an unrelated process of the user. The invariant (INV-MUTATION-AUTHORITY, owner, 2026-09-24):

    Mutation, fault injection, test failure, probe result, or implementation-under-test output MUST NOT expand
    host-side destructive authority. Authority to kill, delete, clean, release, terminate, or mutate external
    resources MUST come exclusively from an independently established controller view.

    The implementation-under-test may REDUCE confidence to RESIDUAL_OWNERSHIP_UNKNOWN. It may NEVER expand
    destructive authority. (MUTATED CODE CAN REDUCE TEST CORRECTNESS, BUT CAN NEVER EXPAND THE RUNNER'S HOST
    CLEANUP AUTHORITY.)

The static half is `destructive_authority.py`: every destructive call site is ledgered with its authority source.
"""

from __future__ import annotations

import dataclasses
import os
import signal
import subprocess
import time

POSIX = os.name == "posix"
RESIDUAL_OWNERSHIP_UNKNOWN = "RESIDUAL_OWNERSHIP_UNKNOWN"
_SLACK_S = 0.5  # births are whole seconds in the table's own clock; the boundary is read in that same clock


@dataclasses.dataclass(frozen=True)
class Boundary:
    """What the runner owns: everything born after `since` whose parent chain reaches `runner`. `since` is the birth,
    in the host table's own clock, of the reader that established the boundary — the same clock every candidate's
    birth is read in, so no wall-clock drift can move the line (Linux derives births from a boot time that jitters)."""
    runner: int
    since: float  # epoch seconds, as the host table reports births
    root: str  # the work tree the workers run from (for stray discovery by command line)


@dataclasses.dataclass(frozen=True)
class Host:
    pid: int
    ppid: int
    pgid: int
    born: float  # epoch seconds, whole
    command: str


@dataclasses.dataclass
class Report:
    signalled: list[dict] = dataclasses.field(default_factory=list)  # {"kind", "id", "proof"} per signal sent
    unproven: list[dict] = dataclasses.field(default_factory=list)  # {"kind", "id", "why"}: never signalled

    @property
    def residual_ownership_unknown(self) -> bool:
        return bool(self.unproven)


class Unproven(Exception):
    """RESIDUAL_OWNERSHIP_UNKNOWN: a cleanup candidate whose ownership this module could not prove."""


def establish(root) -> Boundary:
    """Call before spawning the first worker of a target: the birth floor is the birth of this call's own table
    reader, in the table's clock (falls back to the wall clock only when the reader did not list itself)."""
    table, reader = _read()
    since = table[reader].born if reader in table else time.time()
    return Boundary(os.getpid(), since, str(root))


def host_table() -> dict[int, Host]:
    """This module's own reading of the host: pid, ppid, pgid, start time, command. POSIX: `ps`, zombies included (a
    zombie leader still pins its group id). Windows: Win32_Process through PowerShell — pid, parent, creation time,
    command; there is no process group, so a group is never provable there (pgid -1)."""
    return _read()[0]


def _read() -> tuple[dict[int, Host], int]:
    """(table, pid of the reader process that produced it — it lists itself, and its birth dates the reading)."""
    if not POSIX:
        return _windows_table()
    proc = subprocess.Popen(["ps", "-A", "-o", "pid=,ppid=,pgid=,lstart=,command="], stdout=subprocess.PIPE,
                            encoding="utf-8", errors="replace")
    stdout, _ = proc.communicate()
    out = {}
    for line in stdout.splitlines():
        f = line.split(None, 8)  # pid ppid pgid Www Mmm dd HH:MM:SS yyyy command
        if len(f) < 8:
            continue
        try:
            born = time.mktime(time.strptime(" ".join(f[3:8]), "%a %b %d %H:%M:%S %Y"))
        except ValueError:
            continue
        out[int(f[0])] = Host(int(f[0]), int(f[1]), int(f[2]), born, f[8] if len(f) > 8 else "")
    return out, proc.pid


def _windows_table() -> tuple[dict[int, Host], int]:
    script = ("Get-CimInstance Win32_Process | ForEach-Object { '{0}|{1}|{2}|{3}' -f $_.ProcessId, $_.ParentProcessId, "
              "[int64]((Get-Date $_.CreationDate).ToUniversalTime() - (Get-Date '1970-01-01')).TotalSeconds, $_.CommandLine }")
    try:
        proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                stdout=subprocess.PIPE, encoding="utf-8", errors="replace")
        stdout, _ = proc.communicate(timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return {}, -1  # nothing provable: every candidate is RESIDUAL_OWNERSHIP_UNKNOWN
    out = {}
    for line in stdout.splitlines():
        f = line.split("|", 3)
        try:
            out[int(f[0])] = Host(int(f[0]), int(f[1]), -1, float(f[2]), f[3] if len(f) > 3 else "")
        except (ValueError, IndexError):
            continue
    return out, proc.pid


def owned(boundary: Boundary, table: dict[int, Host] | None = None) -> dict[int, Host]:
    """The processes proved to be the runner's: born no earlier than the boundary, parent chain to the runner.
    The runner itself is not in the set — it is never a cleanup target."""
    table = host_table() if table is None else table
    children: dict[int, list[Host]] = {}
    for p in table.values():
        if p.ppid != p.pid:
            children.setdefault(p.ppid, []).append(p)
    out: dict[int, Host] = {}
    frontier = [boundary.runner]
    while frontier:
        parent = frontier.pop()
        for p in children.get(parent, []):
            if p.pid in out or p.born < boundary.since - _SLACK_S:
                continue  # older than the boundary: a reused pid, or a process the boundary does not cover
            out[p.pid] = p
            frontier.append(p.pid)
    return out


def strays(boundary: Boundary, table: dict[int, Host] | None = None) -> list[Host]:
    """Processes whose command line names the work tree — candidates only; `signal_owned` still proves each."""
    table = host_table() if table is None else table
    marks = {boundary.root, os.path.realpath(boundary.root)}
    return sorted((p for p in table.values() if p.pid != os.getpid() and any(m in p.command for m in marks)),
                  key=lambda p: p.pid)


def prove_member(boundary: Boundary, pid: int, group: int, table: dict[int, Host] | None = None) -> Host | None:
    """A pid CLAIMED by a subject or a fixture (a pid file, a report) is a lookup key, never permission. It is the
    runner's only when, in this module's own table, it sits in `group` — a group the controller created, whose
    leader is proved the runner's — and was born no earlier than the boundary (a reused pid is not it)."""
    table = host_table() if table is None else table
    mine = owned(boundary, table)
    leader, member = mine.get(group), table.get(pid)
    if leader is None or leader.pgid != leader.pid or member is None:
        return None
    if member.pgid != group or member.born < boundary.since - _SLACK_S:
        return None
    return member


def signal_member(boundary: Boundary, pid: int, group: int, sig=None, dry_run: bool = False,
                  table: dict[int, Host] | None = None) -> Report:
    """Signal one claimed pid, only once `prove_member` has proved it; refuse otherwise (INV-MUTATION-AUTHORITY)."""
    sig = getattr(signal, "SIGKILL", signal.SIGTERM) if sig is None else sig
    table = host_table() if table is None else table
    report = Report()
    member = prove_member(boundary, pid, group, table)
    if member is None:
        why = ("not in the host table" if pid not in table else
               "not a member of a group the controller created, or born before the boundary")
        report.unproven.append({"kind": "pid", "id": int(pid), "why": why})
        return report
    proof = {"pid": member.pid, "ppid": member.ppid, "pgid": member.pgid, "born": member.born,
             "runner": boundary.runner, "since": boundary.since, "command": member.command[:120]}
    if not dry_run:
        try:
            os.kill(member.pid, sig)
        except OSError:
            pass  # already gone
    report.signalled.append({"kind": "pid", "id": member.pid, "proof": proof})
    return report


def signal_owned(boundary: Boundary, pids=(), groups=(), sig=None, dry_run: bool = False,
                 table: dict[int, Host] | None = None) -> Report:
    """Signal the candidates this module can prove are the runner's; refuse the rest. `pids` and `groups` are what
    code under mutation reported — never trusted, only checked. `dry_run` proves the selection without sending."""
    sig = getattr(signal, "SIGKILL", signal.SIGTERM) if sig is None else sig  # Windows has no SIGKILL
    table = host_table() if table is None else table
    mine = owned(boundary, table)
    report = Report()
    seen: set[tuple[str, int]] = set()
    for kind, ids in (("group", groups), ("pid", pids)):
        for ident in ids:
            if (kind, int(ident)) in seen:
                continue
            seen.add((kind, int(ident)))
            leader = mine.get(int(ident))
            if leader is None or (kind == "group" and leader.pgid != leader.pid):
                why = ("not in the host table" if int(ident) not in table else
                       "born before the boundary or not a descendant of the runner" if int(ident) not in mine else
                       "not the leader of its group")
                report.unproven.append({"kind": kind, "id": int(ident), "why": why})
                continue
            proof = {"pid": leader.pid, "ppid": leader.ppid, "pgid": leader.pgid, "born": leader.born,
                     "runner": boundary.runner, "since": boundary.since, "command": leader.command[:120]}
            if not dry_run:
                try:
                    if kind == "group":
                        os.killpg(leader.pid, sig)
                    else:
                        os.kill(leader.pid, sig)
                except OSError:
                    pass  # already gone
            report.signalled.append({"kind": kind, "id": leader.pid, "proof": proof})
    return report
