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

import base64
import binascii
import dataclasses
import os
import pathlib
import re
import signal
import subprocess
import sys
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


class TableUnreadable(OSError):
    """A reading of the host (the process table, the environments, the working directories) cannot be taken as the tool
    printed it: the tool failed, did not list this process, or printed a line that is not a row. An OSError, so every
    caller that already stops on "the table cannot be read" (mutation.py `_clean`, `_settle`: HOST_TABLE_UNREADABLE)
    stops on this one too; no partial reading is returned. A line skipped is a process the reading cannot see, and a
    line made up is one that is not there — a command line is implementation output, so neither may be silent."""


def establish(root) -> Boundary:
    """Call before spawning the first worker of a target: the birth floor is the birth of this call's own table
    reader, in the table's clock (falls back to the wall clock only when the reader did not list itself)."""
    table, reader = _read()
    since = table[reader].born if reader in table else time.time()
    return Boundary(os.getpid(), since, str(root))


def host_table() -> dict[int, Host]:
    """This module's own reading of the host: pid, ppid, pgid, start time, command. POSIX: `ps`, zombies included (a
    zombie leader still pins its group id). Windows: Win32_Process through PowerShell — pid, parent, creation time,
    command; there is no process group, so a group is never provable there (pgid -1). POSIX: TableUnreadable (an
    OSError) when `ps` fails, does not list itself, or prints a line that is no row — an empty or partial reading never
    stands for "everything is gone", and a command line never makes or hides a row."""
    return _read()[0]


#: one `ps -A -o pid=,ppid=,pgid=,lstart=,command=` row: ASCII digits, `lstart` as `Www Mmm dd HH:MM:SS yyyy` (the day
#: padded with spaces below 10: `Oct  6`), then the command as printed. Only ASCII spaces separate the columns, so a
#: command that starts with a no-break or ideographic space keeps it. macOS pads the `lstart` column to five spaces,
#: procps to one; the padding cannot be told from leading spaces of the command, and is not part of it.
_PS_ROW = re.compile(r" *([0-9]+) +([0-9]+) +([0-9]+) +([A-Za-z]{3}) ([A-Za-z]{3}) +([0-9]{1,2}) "
                     r"([0-9]{2}:[0-9]{2}:[0-9]{2}) ([0-9]{4})(?: +(.*))?")
#: one `ps -E -ww -A -o pid=,command=` row: the pid, then the command and its environment as printed
_PS_ENV_ROW = re.compile(r" *([0-9]+)(?: +(.*))?")
#: one Windows row, as the PowerShell script prints it: pid|ppid|seconds since 1970|base64 of the UTF-8 command line
_WIN_ROW = re.compile(r"([0-9]+)\|([0-9]+)\|(-?[0-9]+)\|([A-Za-z0-9+/]*={0,2})")


def _lines(raw: bytes) -> list[str]:
    """The non-blank lines of a tool's output. A line ends at "\n" and nowhere else: `ps` and `lsof` escape LF in what
    they print (macOS also CR, VT, FF) but print U+2028, U+2029 and the like raw, so `str.splitlines()` — and a text-mode
    read, which also turns CR into LF — cut a command in two: the tail was dropped, or made a row of a process that is
    not there. Bytes, each line decoded with replacement."""
    return [line for line in (b.decode("utf-8", "replace") for b in raw.split(b"\n")) if line.strip(" ")]


def _not_a_row(tool: str, line: str) -> TableUnreadable:
    return TableUnreadable(f"{tool} printed a line that is not a process row: {line[:80]!r}")


def _twice(tool: str, pid: str, line: str) -> TableUnreadable:
    return TableUnreadable(f"{tool} listed pid {pid} twice: {line[:80]!r}")   # a process is listed once; a row made up


def _ps_env() -> dict[str, str]:
    """The environment `ps` runs in. Its `lstart` is printed in the locale's own words (measured on macOS under
    de_DE.UTF-8: `Di. 13 Okt. 08:03:59 2026`), which the row pattern is not: LC_TIME is pinned to C. LC_ALL would
    override it, so its value moves to LC_CTYPE — the category that decides how the bytes of a command are printed."""
    env = dict(os.environ)
    if "LC_ALL" in env:
        env["LC_CTYPE"] = env.pop("LC_ALL")
    env["LC_TIME"] = "C"
    return env


def _ps_rows(raw: bytes) -> dict[int, Host]:
    """Every line of `ps -A -o pid=,ppid=,pgid=,lstart=,command=` is a row, or the reading is refused (TableUnreadable):
    a pid listed twice, a date that is no date, a line of any other shape. Whole or not returned — never a table with a
    process the reader skipped or one it made up."""
    out: dict[int, Host] = {}
    for line in _lines(raw):
        m = _PS_ROW.fullmatch(line)
        if m is None:
            raise _not_a_row("ps", line)
        pid, ppid, pgid, wday, month, day, clock, year, command = m.groups()
        try:
            born = time.mktime(time.strptime(f"{wday} {month} {day} {clock} {year}", "%a %b %d %H:%M:%S %Y"))
        except (ValueError, OverflowError):
            raise _not_a_row("ps", line) from None
        if int(pid) in out:
            raise _twice("ps", pid, line)
        out[int(pid)] = Host(int(pid), int(ppid), int(pgid), born, command or "")
    return out


def _read() -> tuple[dict[int, Host], int]:
    """(table, pid of the reader process that produced it — it lists itself, and its birth dates the reading).
    TableUnreadable (an OSError) when `ps` fails, does not list itself, or prints a line that is no row."""
    if not POSIX:
        return _windows_table()
    proc = subprocess.Popen(["ps", "-A", "-o", "pid=,ppid=,pgid=,lstart=,command="], stdout=subprocess.PIPE,
                            env=_ps_env())
    raw, _ = proc.communicate()
    if proc.returncode != 0:   # what a failed ps printed is not read: a partial table reads as "every process gone"
        raise TableUnreadable(f"ps -A exited {proc.returncode}: the host table cannot be read")
    out = _ps_rows(raw)
    if proc.pid not in out:
        raise TableUnreadable("ps -A did not list itself: the host table cannot be read")
    return out, proc.pid


def _win_rows(raw: bytes) -> dict[int, Host]:
    """The PowerShell output: one `pid|ppid|seconds|base64` row per line, CR LF terminated — or TableUnreadable."""
    out: dict[int, Host] = {}
    for line in _lines(raw.replace(b"\r\n", b"\n")):
        m = _WIN_ROW.fullmatch(line)
        if m is None:
            raise _not_a_row("powershell", line)
        pid, ppid, born, command = m.groups()
        try:
            text = base64.b64decode(command, validate=True).decode("utf-8", "replace")
        except binascii.Error:
            raise _not_a_row("powershell", line) from None
        if int(pid) in out:
            raise _twice("powershell", pid, line)
        out[int(pid)] = Host(int(pid), int(ppid), -1, float(born), text)
    return out


def _windows_table() -> tuple[dict[int, Host], int]:
    # the command line travels as base64 of its UTF-8 bytes: it may hold any character, a raw CR or LF included, and
    # what is printed is ASCII, one row per line — a command line cannot end a row or begin another
    script = ("Get-CimInstance Win32_Process | ForEach-Object { '{0}|{1}|{2}|{3}' -f $_.ProcessId, $_.ParentProcessId, "
              "[int64]((Get-Date $_.CreationDate).ToUniversalTime() - (Get-Date '1970-01-01')).TotalSeconds, "
              "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$_.CommandLine)) }")
    try:
        proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                stdout=subprocess.PIPE)
        raw, _ = proc.communicate(timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return {}, -1  # nothing provable: every candidate is RESIDUAL_OWNERSHIP_UNKNOWN
    return _win_rows(raw), proc.pid


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


def _env_rows(raw: bytes) -> dict[int, str]:
    """`ps -E -ww -A -o pid=,command=`: {pid: the command and its environment as printed}. macOS escapes LF in an
    environment string as it does in a command, but prints U+2028 and the like raw; a line that is no row, or a pid
    listed twice, is TableUnreadable — an environment string may hold any text, so it never ends a row."""
    out: dict[int, str] = {}
    for line in _lines(raw):
        m = _PS_ENV_ROW.fullmatch(line)
        if m is None:
            raise _not_a_row("ps -E", line)
        if int(m[1]) in out:
            raise _twice("ps -E", m[1], line)
        out[int(m[1])] = m[2] or ""
    return out


def _lsof_cwds(raw: bytes) -> dict[int, str]:
    """`lsof ... -F0pn` -> {pid: working directory}. `-0` ends each field at NUL, which no path holds, and each set at
    LF: a path with U+2028 (or, were one printed raw, an LF) is one field. A field that is not `p<digits>`, `f...` or
    `n...`, or output that stops inside a field, is TableUnreadable."""
    *fields, tail = raw.split(b"\0")
    if tail not in (b"", b"\n"):
        raise TableUnreadable(f"lsof output ends inside a field: {tail[:80]!r}")
    out: dict[int, str] = {}
    pid = None
    for field in fields:
        field = field[1:] if field[:1] == b"\n" else field
        kind, value = field[:1], field[1:].decode("utf-8", "replace")
        if kind == b"p" and re.fullmatch("[0-9]+", value):
            pid = int(value)
        elif kind == b"n" and pid is not None:
            out[pid] = value
        elif kind != b"f":
            raise TableUnreadable(f"lsof printed a field that is not p, f or n of a process: {field[:80]!r}")
    return out


def carriers(prefix: str, table: dict[int, Host] | None = None) -> list[Host]:
    """Processes whose environment holds `prefix` (the mutation runner's `AISEF_MUTATION_RUN=<worker>:`) — candidates
    only, like `strays`; `signal_owned` still proves each. A child given its own environment does not carry it, and
    macOS hides a platform binary's environment (measured 2026-10-07: an inherited token is visible in `ps -E` for a
    Homebrew python3, invisible for /bin/sleep). Read-only: Linux /proc/<pid>/environ, macOS `ps -E`; Windows: none (a
    job has no breakaway)."""
    table = host_table() if table is None else table
    if not POSIX:
        return []
    hits: set[int] = set()
    if sys.platform.startswith("linux"):
        for pid in table:
            try:
                env = pathlib.Path(f"/proc/{pid}/environ").read_bytes()
            except OSError:
                continue
            if any(v.startswith(prefix.encode()) for v in env.split(b"\0")):
                hits.add(pid)
    else:
        proc = subprocess.Popen(["ps", "-E", "-ww", "-A", "-o", "pid=,command="], stdout=subprocess.PIPE)
        raw, _ = proc.communicate()
        if proc.returncode != 0:   # fail closed, as host_table does
            raise TableUnreadable(f"ps -E exited {proc.returncode}: the environments cannot be read")
        listed = _env_rows(raw)
        if proc.pid not in listed:
            raise TableUnreadable("ps -E did not list itself: the environments cannot be read")
        hits.update(pid for pid, text in listed.items() if prefix in text)
    return sorted((table[p] for p in hits if p in table and p != os.getpid()), key=lambda p: p.pid)


def cwd_under(prefix: str, table: dict[int, Host] | None = None, since: float | None = None) -> list[Host]:
    """Processes whose working directory starts with `prefix` (a directory given with its trailing separator, or a
    name prefix) — candidates only, like `strays` and `carriers`; `signal_owned` still proves each. They need neither a
    token nor a path in their command line: a helper given its own environment, or an Apple platform binary whose
    environment `ps -E` hides, still has the cwd it inherited. `since`: only processes born no earlier than this are
    asked (a leftover of a boundary was born after it), which keeps the read cheap. Read-only: Linux /proc/<pid>/cwd,
    macOS `lsof -d cwd` (OSError when it does not list this process, which it is always asked about); Windows: none."""
    table = host_table() if table is None else table
    if not POSIX:
        return []
    head, tail = os.path.split(prefix)
    marks = {prefix, os.path.join(os.path.realpath(head), tail)}
    pids = sorted(p.pid for p in table.values() if p.pid != os.getpid() and (since is None or p.born >= since - _SLACK_S))
    cwd: dict[int, str] = {}
    if sys.platform.startswith("linux"):
        for pid in pids:
            try:
                cwd[pid] = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                continue
    else:
        asked = ",".join(map(str, [os.getpid(), *pids]))
        raw = subprocess.run(["lsof", "-nP", "-w", "-a", "-d", "cwd", "-F0pn", "-p", asked], capture_output=True).stdout
        cwd = _lsof_cwds(raw)
        if os.getpid() not in cwd:   # lsof exits 1 when an asked pid is gone; an empty answer would read as "none"
            raise TableUnreadable("lsof did not list this process's cwd: the working directories cannot be read")
    hits = [p for p, d in cwd.items() if p != os.getpid() and any((d + os.sep).startswith(m) for m in marks)]
    return sorted((table[p] for p in hits if p in table), key=lambda p: p.pid)


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
