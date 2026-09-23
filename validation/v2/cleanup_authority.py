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
process is preferable to signalling an unrelated process of the user. The invariant:

    MUTATED CODE CAN REDUCE TEST CORRECTNESS, BUT CAN NEVER EXPAND THE RUNNER'S HOST CLEANUP AUTHORITY.
"""

from __future__ import annotations

import dataclasses
import os
import signal
import subprocess
import time

POSIX = os.name == "posix"
RESIDUAL_OWNERSHIP_UNKNOWN = "RESIDUAL_OWNERSHIP_UNKNOWN"
_SLACK_S = 1.0  # `ps` reports a start time to the second


@dataclasses.dataclass(frozen=True)
class Boundary:
    """What the runner owns: everything born after `since` whose parent chain reaches `runner`."""
    runner: int
    since: float  # epoch seconds
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
    """Call before spawning the first worker of a target: the birth floor is now."""
    return Boundary(os.getpid(), time.time(), str(root))


def host_table() -> dict[int, Host]:
    """This module's own reading of the host: pid, ppid, pgid, start time, command (POSIX `ps`; zombies included, a
    zombie leader still pins its group id)."""
    if not POSIX:
        return {}
    r = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,lstart=,command="], capture_output=True,
                       encoding="utf-8", errors="replace", check=True)
    out = {}
    for line in r.stdout.splitlines():
        f = line.split(None, 8)  # pid ppid pgid Www Mmm dd HH:MM:SS yyyy command
        if len(f) < 8:
            continue
        try:
            born = time.mktime(time.strptime(" ".join(f[3:8]), "%a %b %d %H:%M:%S %Y"))
        except ValueError:
            continue
        out[int(f[0])] = Host(int(f[0]), int(f[1]), int(f[2]), born, f[8] if len(f) > 8 else "")
    return out


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


def signal_owned(boundary: Boundary, pids=(), groups=(), sig=signal.SIGKILL, dry_run: bool = False,
                 table: dict[int, Host] | None = None) -> Report:
    """Signal the candidates this module can prove are the runner's; refuse the rest. `pids` and `groups` are what
    code under mutation reported — never trusted, only checked. `dry_run` proves the selection without sending."""
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
