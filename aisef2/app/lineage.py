"""A lineage of continued runs (V2.1, `aisef bundle continue` / `aisef run --parent`): who may continue a run, what the
journal does not confirm, what the lineage spent — each decided from evidence, never assumed.

**The journal, exactly.** An event is appended by one `write` and one `fsync` (aisef2/journal/format3.py). That makes
the append *complete* when `write` returned (other processes see it; a killed writer does not lose it) and *durable*
when `fsync` returned (a power loss does not lose it). It does not make it *atomic*: a write may be short — on a crash,
a power loss, or a fatal signal arriving during a multi-page write — and a writer that dies before it truncates leaves
a torn last line. The reader then gives the verified prefix and `torn_tail`. Neither says anything about *effects*:
an event records an effect that already happened (git moved main; a request reached the provider) or a decision about
one. A missing or torn event means the record of an effect is missing — not that the effect did not happen. So a
continuation never assumes the last effects undone: it reconciles them (`reconcile`) against git and against the
journal's own operation identities, and what it cannot attribute is refused unless the operator leaves it out by name.

**One continuation per run, decided by evidence.** `claim` creates `CONTINUED-BY.json` exclusively (the first
generation; a later one is `CONTINUED-BY.<n>.json`), naming the child run and its claimant (host, pid, the process's
start time). Exclusive creation only proves one process won at that moment, so an existing claim is reconciled before
another run may continue the same predecessor:

| the claim's child | the claimant | decision |
|---|---|---|
| BEGUN (its journal reads and holds an event) | — | refused: the lineage continues from the child — never a fork |
| ENDED_UNBEGUN (a record that says it ended before it began — it names no journal of events — and no journal) | done | superseded: a new generation records the evidence |
| UNBEGUN (no record, no journal, or a journal of no bytes) | provably gone (same host, the pid absent or another process) | superseded, with the evidence |
| UNBEGUN | alive, on another host, or not decidable | refused; the operator may supersede by naming the claim's sha256 (recorded as their assertion) |
| UNREAD (evidence there that cannot be read: see below) | whatever it is | refused; only the operator's sha256 supersedes (recorded as their assertion, with the cause) — and the run is then still refused while that evidence does not read or is gone (`unread`, below) |

Nothing is deleted: a superseded claim stays, the new generation points at it. A child whose journal reads and holds an
event began and is never superseded, by evidence or by assertion. **A child whose evidence is there and cannot be read
is not one that did not begin** (it is UNREAD, never UNBEGUN): a directory the system will not let this process search,
a journal it will not open, one that does not reconstruct, one that holds bytes and no complete event; a link or a file
where the journal's path should lead; a record that names a journal of events where there is none, or none that holds a
byte, or one that is there and is not a record. That the evidence of the beginning is damaged says nothing about
whether the child began, and the claimant's absence is evidence about a process, not about the child's run; so no
evidence supersedes it — and a failure to read releases and takes nothing. What is genuinely not there (nothing on the
path at all) is still not evidence of a beginning. The claim is taken before the run's first provider request, so a run
that loses the race spends nothing.

**A predecessor this process may not list, search or write** is a refusal (`LineageRefused`, which `aisef run` answers
with exit 2 and `aisef bundle continue` with `refused:`), never a traceback and never "no claims": the generations of
a directory whose listing is denied cannot be told, and the newest decides.

**Spend.** `account_of` re-derives a run's spend from its evidence alone (the Budget's rules: sessions, journaled
requests, the preflight's ledger) and adds what only the journal shows: a provider request with no result — in flight
when the run ended — whose session stream exists is unknown spend. `lineage_account` sums the lineage (each run once,
and every superseded child, whose preflight may have spent). Evidence the system will not let `account_of` look at — a
run directory with no search permission, a `sessions` that is a link into a directory that cannot be traversed or is a
directory that cannot be listed, a journal that is there and cannot be read (what it recorded is the provider
requests) — is unknown spend, listed: never raised out of it, never a 0 shown as known. So is a journal that reads and
is not the one the run's own RUN.json names (its digest and length: emptied, cut at a line or in one, replaced). What is
genuinely not there (no sessions directory, no ledger, a run directory nothing names) is what `account_of` takes for a
run that spent nothing there — unless the run itself says it existed (below, "Evidence that is gone"); `lineage_account`
is stricter about a run a record NAMES as the one it continues (below).

**Two kinds of unknown, and what a continuation may do about each.** The sums a lineage account holds are what its
readable parts spent — exact, per run in `runs` — and a lower bound on the lineage's total whenever `unaccounted` is not
empty (`total` is then None): the total is unknown while any part is, and no sum stands for it. What the evidence READS and
says was sent and never answered (a request in flight, a session that finished no step, a preflight request with no
answer) is unknown spend with a cause: a continuation starts no paid work unless the operator accepts it by name
(`--accept-unaccounted`, recorded), and the lineage's known spend counts against the run's ceilings (continuing never
resets a budget; the budget account names what was accepted). What the evidence CANNOT BE READ for (`unread`: a journal,
a ledger or a session stream that is there and does not read — whatever stands on the journal's path, a link to
nothing included; a record or a claim that cannot be read, so the run it names — a predecessor, a superseded child — is
not known) is a part that was not reconciled at all, not one whose request count is known: no flag skips it, and the
operator's assertion that a claim is superseded (`--supersede-claim`) does not make its child's spend known. A run that
a record NAMES as the one it continues existed (`aisef run --parent` refuses a parent with no run record): when its
directory is not there, is a file, or is a link that leads nowhere, what it spent is `unread` — not a run that spent
nothing. (A superseded child a claim names, whose directory is not there, stays UNBEGUN: it spent nothing there.) A
record or a claim that is a link to nothing, or one that loops, is there and cannot be read, like one that is cut.
`aisef run --parent` is refused until the evidence is readable again (restored from a faithful copy, its permissions
given back); where that cannot be, the lineage cannot be continued and a run without `--parent` inherits nothing.
Nothing of the lineage's evidence is written or changed by the refusal. A run refused after its claim leaves its own
record and the one claim generation it took on the predecessor — append-only history, and with `--supersede-claim` the
operator's recorded assertion — and no claim is superseded by a read that failed: by evidence, or by the operator naming
its sha256, which is not evidence about what the child spent.

**Evidence that is gone (owner decision 2026-10-15).** A sessions directory, a session stream or the preflight's ledger
that is not there beside a journal that reads is not a run that spent less: a number that looks reconciled over a spend
no evidence shows is what the decision forbids. Two witnesses say the evidence existed, and a run they show it for is
UNREAD (cost unknown, `exact` False, `total` None, `aisef run --parent` refused whatever the flags, as for any unread
part): (1) the run's own RUN.json — its `budget.spent`, less the `budget.inherited` share, is the Budget's account of
the same evidence when the run ended (a run that failed before its Budget was built: its `preflight.accounting`, which is
all it spent), so a counter the record holds and the evidence now re-derives LESS of (the four counters, and the number of
session streams) is spend whose evidence has gone; (2) with no record that names a spend (a run killed before RUN.json
was written, or while it was), a provider request the journal records as answered — a result that is not a closer's —
that no session stream stands for. What the run's record vouches for (its counters equal what the evidence re-derives) is
not gone, whatever the journal: a session that never started (a budget reached, a reviewer that could not run) leaves a
request and no stream. Without a record the two cannot be told apart, and (2) takes the unknown — saying so: where no
session started there is no stream to restore, and the lineage cannot be continued. A request in flight (no result) is
neither: it is spend that READS as unknown, accepted by name (`--accept-unaccounted`) as before. The figures the run keeps
are what is left, attributed to it and no more exact than that. Nothing is rewritten and no claim is released because of
it. What neither witness reaches (a limit, not a promise): with no record the journal does not hold the preflight's
requests, so a preflight ledger that is gone beside a record that does not read is not seen; and (2) pairs answered
requests with streams by COUNT per story and role, as the in-flight check does — a stream's name is the kernel's attempt
number, which a request does not follow (a reviewer is not reached on an attempt whose proof failed).

**A file that is damaged, or is not what a run writes** — a ledger line or a claim that is valid JSON and no object, a
session stream the reader refuses — is answered as the torn form of the same file is: unknown spend, listed; the
unreadable-claim marker; a claim passed over, or not superseded without evidence (`LineageRefused`). `claim`,
`continued_by`, `predecessor_of`, `account_of` and `lineage_account` raise nothing else for such a file."""

from __future__ import annotations

import errno
import json
import os
import pathlib
import re
import socket
import stat
import subprocess
from typing import Mapping

STARTED = "RUN.started.json"
CLAIM = "CONTINUED-BY.json"
JOURNAL = pathlib.Path("run") / "journals" / "aisef-run.jsonl"
BEGUN, ENDED_UNBEGUN, UNBEGUN, UNREAD = "BEGUN", "ENDED_UNBEGUN", "UNBEGUN", "UNREAD"
SPEND = ("provider_requests", "turns", "input_tokens", "output_tokens")


class LineageRefused(Exception):
    """The lineage cannot be continued as asked: nothing was started."""


def _sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _claimed_run(text: str) -> str | None:
    """The run a claim file names (None: it names none). A file that parses but is no claim — not a JSON object, or one
    that names its run by anything but a string — is as unreadable as a torn one: ValueError, which every reader of a
    claim already answers (a marker, or the claim passed over)."""
    doc = json.loads(text)
    if not isinstance(doc, dict) or not isinstance(doc.get("run", ""), str) or "\0" in doc.get("run", ""):
        raise ValueError("not a claim")     # a name with a NUL byte names no run: `Path.resolve` raises on it, not a refusal
    return doc.get("run")


#: what `continued_by` answers for a newest claim that cannot be read: a name no run has, and no state (the pair it has
#: always returned); a report states it UNREAD with the cause (`claim_unread`)
UNREADABLE_CLAIM = "(an unreadable claim)"


# ------------------------------------------------------------------------------------------------ claims

def claims(predecessor: pathlib.Path) -> list[tuple[int, pathlib.Path]]:
    """The claim generations on `predecessor`, oldest first. A directory the system will not let this process list and
    search is not "no claims" (`_look`): `glob` answers an empty listing for what it cannot list, so the later
    generations were not seen and the first, found by its name, was taken for the newest — `LineageRefused`."""
    try:
        _look(predecessor)
        _look(predecessor / CLAIM)
    except OSError as e:
        raise LineageRefused(f"{predecessor}: its claims cannot be listed ({type(e).__name__}: {e.strerror or e}): a "
                             "lineage cannot be known from a directory this process may not list and search — restore "
                             "its permissions (nothing was taken or released)") from None
    out = [(1, predecessor / CLAIM)] if os.path.lexists(predecessor / CLAIM) else []   # a link to nothing is a claim there
    for p in predecessor.glob("CONTINUED-BY.*.json"):
        m = re.fullmatch(r"CONTINUED-BY\.(\d+)\.json", p.name)
        if m and int(m[1]) >= 2:
            out.append((int(m[1]), p))
    return sorted(out)


def events_of(run_dir: pathlib.Path) -> tuple[list, bool] | None:
    """The run's journal events and whether its tail is torn, or None when it has no journal that reconstructs."""
    from aisef2.journal import format3
    try:
        j = format3.reconstruct((run_dir / JOURNAL).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a journal the reader refuses is no journal for this purpose
        return None
    return list(j.events), bool(j.torn_tail)


def child_evidence(child: pathlib.Path) -> tuple[str, str | None]:
    """(the child's state, and why when it is UNREAD). BEGUN: its journal reads and holds an event. UNREAD: its evidence
    is there and cannot be read — the journal cannot be opened (a directory of it that cannot be searched, a file with
    no read permission, a directory in its place), is not text, does not reconstruct, or holds bytes and no complete
    event (a first line that was cut); a link that leads nowhere or a file stands on its path; or the record names a
    journal of events and there is none (`_without_a_journal`). Else the evidence is not there: ENDED_UNBEGUN (a record
    that says it ended before it began) or UNBEGUN (nothing at all, or a journal of no bytes and no record)."""
    from aisef2.journal import format3
    try:
        text = (child / JOURNAL).read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return UNREAD, f"{JOURNAL.name} is not text ({e.reason})"
    except OSError as e:
        if not not_there(e):
            return UNREAD, f"{JOURNAL.name} cannot be read ({type(e).__name__}: {e.strerror or e})"
        text = None
    except ValueError:      # a name with a NUL byte names no file
        return UNBEGUN, None
    if text:
        try:
            events = format3.reconstruct(text).events
        except Exception as e:  # noqa: BLE001 — a journal the reader refuses is evidence that cannot be read, not none
            return UNREAD, f"{JOURNAL.name} does not reconstruct ({type(e).__name__}: {e})"[:300]
        if events:
            return BEGUN, None
        return UNREAD, f"{JOURNAL.name} holds bytes and no complete event (a first line that was cut)"
    if text is None:    # "nothing there" is the system's answer for a link that leads nowhere and a file in a directory's place
        way = _in_the_way(child)
        if way:
            return UNREAD, way
    return _without_a_journal(child, "is not there" if text is None else "holds no bytes")


def _in_the_way(child: pathlib.Path) -> str | None:
    """What stands on the journal's path where the system said "nothing there": a link that leads nowhere or loops, a
    file where a directory should be. That is evidence there and damaged — not an absence. None: nothing is on the
    path (the first name that is missing is missing)."""
    here = child
    for i, part in enumerate(("", *JOURNAL.parts)):
        here = here / part if part else here
        try:
            mode = os.lstat(here).st_mode
            if stat.S_ISLNK(mode):
                try:
                    mode = os.stat(here).st_mode
                except OSError as e:
                    return f"{here} is a link that leads nowhere ({type(e).__name__})"
        except (OSError, ValueError):   # a refusal to look was answered by the read that came here (`child_evidence`)
            return None
        if i < len(JOURNAL.parts) and not stat.S_ISDIR(mode):
            return f"{here} is not a directory: the run's evidence is not where a run writes it"
    return None


def _without_a_journal(child: pathlib.Path, what: str) -> tuple[str, str | None]:
    """The state of a child whose journal holds no event (`what`: it is not there, or holds no bytes). With no record it
    is UNBEGUN. A record is the run's own account: it ended before it began when it names no journal, or one of no
    lines (ENDED_UNBEGUN); a record that names a journal of events — a run that began — and a record that cannot be read
    say nothing that would let the journal's absence be taken for a run that never began: UNREAD."""
    try:
        rec = json.loads((child / "RUN.json").read_text(encoding="utf-8"))
    except OSError as e:
        if not_there(e):
            return UNBEGUN, None
        return UNREAD, f"RUN.json cannot be read ({type(e).__name__}: {e.strerror or e}) and {JOURNAL.name} {what}"
    except ValueError as e:     # not text, or cut: a record that cannot say the run ended before it began
        return UNREAD, f"RUN.json is there and is not a record ({type(e).__name__}) and {JOURNAL.name} {what}"
    if not isinstance(rec, dict):
        return UNREAD, f"RUN.json is there and is not a record (a JSON object) and {JOURNAL.name} {what}"
    j = rec.get("journal")
    if not j:
        return ENDED_UNBEGUN, None
    lines = j.get("lines") if isinstance(j, dict) else None
    if type(lines) is int and lines == 0:
        return ENDED_UNBEGUN, None
    if type(lines) is int:
        return UNREAD, f"RUN.json records a journal of {lines} lines and {JOURNAL.name} {what}: the run began"
    return UNREAD, f"RUN.json's journal is not a journal record (no line count) and {JOURNAL.name} {what}"


def child_state(child: pathlib.Path) -> str:
    return child_evidence(child)[0]


def process_started(pid: int) -> str | None:
    """The start time the system reports for `pid` (a process's identity with its pid: a reused pid starts later), None
    when no such process exists, "unknown" when it cannot be read. Read from the process table only — nothing is sent
    to the process."""
    try:
        p = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    started = p.stdout.strip()
    if not started and (p.returncode != 1 or p.stderr.strip()):
        return "unknown"    # a `ps` that failed answers nothing: "no such process" is empty output, status 1, no message
    return started or None


def claimant() -> dict:
    return {"host": socket.gethostname(), "pid": os.getpid(), "started": process_started(os.getpid())}


def _gone(who: Mapping) -> bool | None:
    """Whether the claimant is provably gone: True (same host, its pid absent or now another process), False (alive),
    None (another host, or its identity cannot be read)."""
    if not isinstance(who, Mapping) or who.get("host") != socket.gethostname() or not isinstance(who.get("pid"), int) \
            or who.get("started") in (None, "unknown"):
        return None
    now = process_started(who["pid"])
    if now is None:
        return True
    return None if now == "unknown" else now != who["started"]


def claim(predecessor: pathlib.Path, child: pathlib.Path, at: float, supersede: str | None = None) -> dict:
    """Take the one continuation `predecessor` may have (module docstring); the claim written, as a dict."""
    found = claims(predecessor)
    supersedes = None
    target = predecessor / CLAIM
    if found:
        n, path = found[-1]
        try:
            data = path.read_bytes()
        except OSError as e:    # what it says cannot be reconciled, nor its digest named: only evidence could supersede it
            raise LineageRefused(f"{predecessor} is claimed ({path.name}) and the claim cannot be read "
                                 f"({type(e).__name__}: {e.strerror or e}): not superseded without evidence — make "
                                 f"{path.name} readable again (its permissions, or a faithful copy of it) and run again; "
                                 "nothing was taken or released") from None
        try:
            doc = json.loads(data)
        except ValueError:
            doc = {}
        if not isinstance(doc, dict):     # JSON that is no claim is as torn as a torn one
            doc = {}
        held = pathlib.Path(str(doc.get("run", "")))
        state, unread = child_evidence(held) if doc.get("run") else (UNBEGUN, None)
        if state == BEGUN:
            raise LineageRefused(f"{predecessor} is continued by {held}, which began: continue the lineage from it")
        gone = True if state == ENDED_UNBEGUN else _gone(doc.get("claimant") or {})
        asserted = supersede is not None and supersede == _sha(data)
        if state == UNREAD and not asserted:    # the claimant's absence is no evidence about a child that may have begun
            raise LineageRefused(f"{predecessor} is claimed by {held} ({path.name}), whose evidence exists and cannot be "
                                 f"read ({unread}): it may have begun (UNREAD), so it is not superseded — not even by its "
                                 f"claimant's absence. Make it readable again (its permissions, or its journal from a "
                                 f"faithful copy) and run again: it is then a child that began (continue from it) or one "
                                 f"that did not; or, having inspected it, assert that it is not to be continued: "
                                 f"--supersede-claim {_sha(data)} (recorded; the run is still refused while that "
                                 "evidence does not read, because what the child spent is not known)")
        if state != UNREAD and gone is not True and not asserted:
            why = "is alive" if gone is False else "cannot be shown gone (another host, or its identity unreadable)"
            raise LineageRefused(f"{predecessor} is claimed by {held} ({path.name}), whose claimant {why} and which has "
                                 f"not begun: not superseded without evidence (an operator may name it: "
                                 f"--supersede-claim {_sha(data)})")
        supersedes = {"claim": path.name, "sha256": _sha(data), "child": str(held), "child_state": state,
                      "claimant_gone": gone, "operator_asserted": asserted and (state == UNREAD or gone is not True),
                      **({"unread": unread} if state == UNREAD else {})}
        target = predecessor / f"CONTINUED-BY.{n + 1}.json"
    doc = {"run": str(child), "claimed": at, "claimant": claimant(), **({"supersedes": supersedes} if supersedes else {})}
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o444)
    except FileExistsError:
        raise LineageRefused(f"{predecessor}: another run took {target.name} at the same moment: a run is continued "
                             "once") from None
    except OSError as e:    # an archived, read-only or unwritable predecessor: the claim is a file in its directory
        full = e.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", None))
        raise LineageRefused(f"{predecessor} cannot be claimed: {target.name} cannot be created ({type(e).__name__}: "
                             f"{e.strerror or e}) — the claim is a file in that directory: "
                             f"{'free space on its volume' if full else 'restore write access to it'} and run again. "
                             "Not from a copy of the run: a copy has claims of its own and the run could be continued "
                             "twice; nothing was taken") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return doc


def continued_by(predecessor: pathlib.Path) -> tuple[str | None, str | None]:
    """(the run the newest claim names, its state), or (None, None)."""
    found = claims(predecessor)
    if not found:
        return None, None
    try:
        run = _claimed_run(found[-1][1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UNREADABLE_CLAIM, None
    return run, child_state(pathlib.Path(run)) if run else None


def claim_unread(predecessor: pathlib.Path) -> str | None:
    """Why the newest claim on `predecessor` cannot be read (the cause, and what the operator does), None when it reads
    or there is none: `continued_by` answers `UNREADABLE_CLAIM` and no state for it, a report states UNREAD with this."""
    found = claims(predecessor)
    if not found:
        return None
    path = found[-1][1]
    try:
        _claimed_run(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return (f"{path.name} cannot be read ({type(e).__name__}: {getattr(e, 'strerror', None) or e})"[:300] +
                ": make it readable again (its permissions, or a faithful copy) — until then `aisef run --parent` "
                "refuses the run (naming the claim's sha256 supersedes the claim, not what its child spent, which "
                "stays unknown), and no claim is ever rewritten")
    return None


# ------------------------------------------------------------------------------------------------ reconciliation

def _git(repo: pathlib.Path, *args: str):
    from aisef2.orchestrate.workspace import git
    return git(repo, *args)


def reconcile(run_dir: pathlib.Path, events: list, baseline: str, torn: bool) -> dict:
    """What `run_dir` did that its journal does not confirm, each item identified against git and the journal's own
    operation identities (module docstring), or not identified."""
    repo = run_dir / "repo"
    candidates = {e.data.get("candidate"): e.data.get("story_id") for e in events
                  if e.type == "proof/verified" and e.data.get("candidate")}
    begun: dict = {}
    for e in events:
        if e.type in ("story/begin", "story/end"):
            begun[e.data["story_id"]] = begun.get(e.data["story_id"], 0) + (1 if e.type == "story/begin" else -1)
    open_stories = {s for s, n in begun.items() if n > 0}
    items: list[dict] = []
    main = _git(repo, "rev-parse", "main").stdout.strip()
    if main != baseline:
        listed = _git(repo, "rev-list", "--first-parent", "--reverse", "--parents", f"{baseline}..{main}")
        for line in listed.stdout.splitlines():
            commit, *parents = line.split()
            subject = _git(repo, "log", "-1", "--format=%s", commit).stdout.strip()
            other = parents[1] if len(parents) == 2 else None
            story = candidates.get(other)
            if other and story in open_stories and subject == f"merge {other[:12]}":
                items.append({"commit": commit, "operation": "merge", "story": story, "candidate": other, "identified": True,
                              "why": f"the kernel's merge of {story}'s proved candidate {other[:12]}: its post-merge proof "
                                     "and commit were never journaled"})
            else:
                items.append({"commit": commit, "operation": "unknown", "identified": False, "subject": subject[:120],
                              "why": "a commit on main no journaled operation of this run accounts for"})
        if not listed.stdout.strip():
            items.append({"commit": main, "operation": "unknown", "identified": False,
                          "why": f"main {main[:12]} does not descend from the journal's last commit {baseline[:12]}"})
    trees = _git(repo, "worktree", "list", "--porcelain").stdout.split("\n\n")
    for block in trees:
        # a line ends at LF only: git prints a path raw, U+2028 and U+2029 in it too (`splitlines()` cut the line there)
        fields = dict(ln.split(" ", 1) for ln in block.split("\n") if " " in ln)
        name = pathlib.Path(fields.get("worktree", "")).name
        m = re.fullmatch(r"wt-(.+)", name)
        head = fields.get("HEAD")
        listed_already = {i["commit"] for i in items}
        if m and m[1] in open_stories and head and head != baseline and head not in candidates \
                and head not in listed_already and _git(repo, "merge-base", "--is-ancestor", head, main).returncode != 0 \
                and _git(repo, "merge-base", "--is-ancestor", baseline, head).returncode == 0:
            items.append({"commit": head, "operation": "candidate", "story": m[1], "identified": True,
                          "why": f"the developer's candidate of {m[1]} in the kernel's worktree {name}, never journaled "
                                 "(no proof ran on it): developed again"})
    cut = None
    if torn:    # what the cut bytes still say (an event is canonical JSON: its type is its LAST field, often lost)
        raw = (run_dir / JOURNAL).read_bytes().rsplit(b"\n", 1)[-1]
        t = re.search(rb'"type":\s*"([a-z/_]+)"', raw)
        cut = {"seq": len(events), "bytes": len(raw), "type": t.group(1).decode() if t else None,
               "stories": sorted({s.decode() for s in re.findall(rb'"story_id":\s*"([^"]+)"', raw)}),
               "why": "the last append was cut: its record is lost; its effects, if any, are among the items reconciled "
                      "against git — never assumed undone"}
    return {"items": items, "unidentified": [i for i in items if not i["identified"]], "cut_event": cut}


# ------------------------------------------------------------------------------------------------ spend

#: what the system answers when there is nothing at a path — the errors pathlib itself (3.11-3.13) takes for "not there":
#: no such name, a component that is not a directory, a link that resolves to nothing or loops; on Windows an invalid
#: name, a drive not ready, a reparse point that cannot be resolved
_NOT_THERE = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_NOT_THERE_WINERROR = (21, 123, 1921)


def not_there(e: OSError) -> bool:
    """Whether `e` is the system's answer for "nothing at that path" (`_NOT_THERE`) and not a refusal to look."""
    return e.errno in _NOT_THERE or getattr(e, "winerror", None) in _NOT_THERE_WINERROR


def _look(path: pathlib.Path) -> None:
    """Raise what keeps the system from listing `path` — or, `path` being a file, from finding it: no permission (a link
    into a directory that cannot be traversed, a run directory with no search permission, a directory that cannot be
    listed), a name too long, an I/O error. Nothing for what is there (a file answers "not a directory") and for what is
    genuinely not there. `Path.is_dir` and `exists` raise on a refusal in 3.11-3.13 and answer False in 3.14, and `glob`
    answers an empty listing in all of them: spend that could not be seen was raised out of `account_of` or shown as a
    known 0."""
    try:
        os.listdir(path)
    except OSError as e:
        if not not_there(e):
            raise
    except ValueError:      # a name with a NUL byte names no file: pathlib has always answered "not there"
        pass


def is_file(path: pathlib.Path) -> bool:
    """`path.is_file()` that does not take a refusal for absence: a component the system will not let this process
    search raised PermissionError out of `is_file` on 3.11-3.13 and answered False on 3.14 ("no record there"). A file
    that is not there is False; one that cannot be looked at is `LineageRefused`, with the cause."""
    try:
        _look(path)
    except OSError as e:
        raise LineageRefused(f"{path} cannot be looked at ({type(e).__name__}: {e.strerror or e}): restore the "
                             "permissions of the run directory") from None
    return path.is_file()


def account_of(run_dir: pathlib.Path) -> dict:
    """What `run_dir` spent, re-derived from its evidence (the run's Budget rules), and what is unknown: `unaccounted`
    lists it all; `unread` is the part of it whose evidence is there and cannot be read (a journal, a ledger, a session
    stream), or that the run's own record or journal shows and is gone (a sessions directory, a stream, the ledger) —
    spend not even a request count is known for, which no acceptance of the operator covers (module docstring)."""
    from aisef2.app import client, preflight
    got = events_of(run_dir)
    events = got[0] if got else []
    requests = [e for e in events if e.type == "provider/request"]
    answered = {s for e in events if e.type == "provider/result" for s in e.source_seqs}
    ledger, sessions = run_dir / "preflight" / "LEDGER.jsonl", run_dir / "sessions"
    unread: list[str] = []
    try:
        _look(ledger)
        pre = preflight.accounting(ledger)
    except Exception as e:  # noqa: BLE001 — a ledger the reader refuses, whatever its damage, is spend that is unknown
        pre = {k: 0 for k in SPEND} | {"unaccounted": []}
        unread.append(f"{run_dir.name}: the preflight's ledger does not read ({type(e).__name__}): what the preflight "
                      "spent is unknown")
    huge = {k: 10 ** 12 for k in SPEND}
    try:
        _look(sessions)
        spent = client.Budget(huge, pre, sessions, lambda: len(requests)).spend()
    except Exception as e:  # noqa: BLE001 — a stream the reader refuses: what the sessions spent is unknown, not 0
        stream = (f"{run_dir.name}: a session's event stream does not read ({type(e).__name__}): what the sessions "
                  "spent is unknown")
        spent = {**{k: pre[k] for k in SPEND}, "provider_requests": pre["provider_requests"] + len(requests),
                 "unaccounted": []}
        unread.append(stream)
    unaccounted = list(spent["unaccounted"]) + unread + [f"preflight request {n} sent and never answered"
                                                           for n in pre.get("unaccounted") or []]
    if got is None:     # no journal that reconstructs: not there is a run that spent nothing there; there and unread is unknown
        state, why = child_evidence(run_dir)
        # nothing there is a run directory that is not one (not there, a file, a link to nothing); a run directory with
        # something on the journal's path that does not read — a link to nothing, a link that loops, a file in a
        # directory's place — has a journal that is there and cannot be read: its requests are unknown, never a 0
        if state == UNREAD and _is_a_directory(run_dir):
            journal = (f"{run_dir.name}: its journal evidence is there and cannot be read ({why}): the provider "
                       "requests it recorded are unknown spend")
            unaccounted.append(journal)
            unread.append(journal)
    bad = _journal_mismatch(run_dir) if got is not None else None
    if bad:     # reads, and is not the journal the run closed: what is missing from it is unknown, not 0 and not a few
        journal = (f"{run_dir.name}: its journal is not the one RUN.json names ({bad}): the provider requests it "
                   "recorded are unknown spend")
        unaccounted.append(journal)
        unread.append(journal)
    logs = [p.name for p in sessions.glob("*.jsonl")] if os.path.isdir(sessions) else []
    gone = None if unread else _evidence_gone(run_dir, events, requests, logs, spent)
    if gone:    # what the run's own record or journal says existed is not there: not a run that spent less
        unaccounted.append(gone)
        unread.append(gone)
    for r in requests:
        if r.seq in answered:
            continue
        story, owner = r.data.get("story_id"), r.data.get("budget_owner")
        role = "developer" if owner == "DEVELOPER" else "reviewer"
        mine = [x for x in logs if x.startswith(f"{story}.{role}.")]
        done = sum(1 for q in requests if q.seq in answered and q.data.get("story_id") == story
                   and q.data.get("budget_owner") == owner)
        if len(mine) > done:
            unaccounted.append(f"{run_dir.name}: provider request seq {r.seq} ({story}, {owner}) has no result — in "
                               "flight when the run ended: what it spent is unknown")
    # `exact`: nothing of this run is unknown, so the four counters are what it spent; else they are a lower bound
    return {"run": str(run_dir), "recorded": os.path.isfile(run_dir / "RUN.json"),
            **{k: int(spent[k]) for k in SPEND}, "unaccounted": unaccounted, "unread": unread, "exact": not unaccounted}


def _journal_mismatch(run_dir: pathlib.Path) -> str | None:
    """RUN.json names the journal the run closed — digest and length, which `--verify` and `bundle continue` compare. A
    journal that reads and is another — emptied, cut at a line or in one, replaced — is not the run's spend, whatever it
    reconstructs to (a crash or a full disk leaves exactly that). Why they differ; None when they agree, or when there is
    nothing to compare (no record, or one that names no digest: a run killed before its record; the journal that does not
    read is `account_of`'s own finding)."""
    try:
        named = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8")).get("journal")
        data = (run_dir / JOURNAL).read_bytes()
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(named, dict) or not isinstance(named.get("sha256"), str):
        return None
    lines = data.count(b"\n")
    if _sha(data) == named["sha256"] and lines == named.get("lines"):
        return None
    return f"{lines} lines on disk, {named.get('lines')} recorded" + ("" if lines != named.get("lines") else "; digest differs")


def _recorded_spend(run_dir: pathlib.Path) -> tuple[dict | None, str | None]:
    """(what RUN.json says the run ITSELF spent, why it cannot be compared). The record's `budget.spent` is the Budget's
    account at the end of the run, the lineage's known share (`budget.inherited`) included: less that share it is the
    four counters of this run's own evidence. A run that built no Budget (it failed after its preflight and before: a
    route that is not attested, say) names the preflight's own account, `preflight.accounting`, which is all it spent.
    (None, None): the record names no spend — there is none, or it is not there or does not read (a run killed while
    it was being written, whose damage `_predecessor` and `child_evidence` answer for the claim, not for the cost: only
    the journal decides there). (None, why): a budget that is there and is not an account of four counts."""
    try:
        doc = json.loads((run_dir / "RUN.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None

    def counts(x) -> bool:
        return isinstance(x, dict) and all(type(x.get(k)) is int and x[k] >= 0 for k in SPEND)
    budget = doc.get("budget") if isinstance(doc, dict) else None
    if budget is None:
        pre = doc.get("preflight") if isinstance(doc, dict) else None
        pre = pre.get("accounting") if isinstance(pre, dict) else None
        return ({k: pre[k] for k in SPEND}, None) if counts(pre) else (None, None)
    spent = budget.get("spent") if isinstance(budget, dict) else None
    shared = budget.get("inherited", dict.fromkeys(SPEND, 0)) if isinstance(budget, dict) else None
    if not counts(spent) or not counts(shared) or any(spent[k] < shared[k] for k in SPEND):
        return None, "RUN.json's budget is not an account of what the run spent (four counts, the inherited share within)"
    own = {k: spent[k] - shared[k] for k in SPEND}
    started = spent.get("sessions_started")     # the session streams there were: a stream that held no step has no counter
    if type(started) is int and started >= 0:
        own["sessions_started"] = started
    return own, None


def _evidence_gone(run_dir: pathlib.Path, events: list, requests: list, logs: list[str], derived: Mapping) -> str | None:
    """Evidence the run left and that is no longer there, though nothing that is there cannot be read: a sessions
    directory or a stream, the preflight's ledger, moved or cut away beside a journal that reads. `account_of` took what
    is not there for a run that spent nothing there, and showed the figures that were left as the run's total — a number
    that looks reconciled and is not (owner decision 2026-10-15). Two witnesses, neither a guess:

    * the run's own record: RUN.json's `budget.spent` is what the Budget derived from this same evidence when the run
      ended (a run that built no Budget: its `preflight.accounting`, all it spent), so a counter the record holds and
      the evidence now re-derives LESS of — the four counters, and the number of session streams there were
      (`sessions_started`: a stream that held no step has no counter) — is spend whose evidence has gone;
    * without a record that names a spend (a run killed before it was written): a provider request the journal records
      as answered (a result that is not a closer's) and that no session stream stands for — a request that is in flight
      (no result) is not that: the evidence of one that never started is not expected, and the pins of `account_of` keep
      it so. Where the record vouches for the figures, an answered request whose session never started is not gone.
      Without a record the two cannot be told apart — a stream that is gone, and a session that never started (a budget
      reached, a reviewer that could not run) leave the same journal — and the rule takes the unknown: the cause says
      so, because then there is nothing to restore and the lineage cannot be continued.

    The cause names what the operator restores; None when nothing is missing."""
    recorded, why = _recorded_spend(run_dir)
    if why:
        return f"{run_dir.name}: {why}: what the run spent cannot be compared with what its evidence shows, so it is unknown"
    if recorded is not None:
        shown = {**{k: int(derived[k]) for k in SPEND}, "sessions_started": len(logs)}
        lacking = [f"{k} {recorded[k]} (the evidence shows {shown[k]})" for k in recorded if recorded[k] > shown[k]]
        if not lacking:
            return None
        return (f"{run_dir.name}: RUN.json records that the run spent {', '.join(lacking)}: the evidence that held the "
                "rest — a sessions directory or a session stream, the preflight's ledger — is not there, so what the run "
                "spent is unknown (the figures kept for it are what is left, not what it spent)")
    answered = {s for e in events if e.type == "provider/result" and not e.data.get("synthetic") for s in e.source_seqs}
    owed: dict[tuple, int] = {}
    for r in requests:
        if r.seq in answered:
            key = (r.data.get("story_id"), "developer" if r.data.get("budget_owner") == "DEVELOPER" else "reviewer")
            owed[key] = owed.get(key, 0) + 1
    lacking = []
    for (story, role), n in owed.items():
        have = sum(1 for x in logs if re.fullmatch(re.escape(str(story)) + rf"\.{role}\.\d+\.jsonl", x))
        if have < n:
            lacking.append(f"{story} {role}: {n} answered, {have} stream{'' if have == 1 else 's'}")
    if not lacking:
        return None
    return (f"{run_dir.name}: the journal records provider requests as answered that no session stream stands for "
            f"({'; '.join(lacking)}) and no record names what the run spent: the evidence of what they spent is not "
            "there, so it is unknown (a session that never started — a budget reached, a reviewer that could not run — "
            "leaves the same journal, and only RUN.json would tell the two apart: where that is what happened there is "
            "no stream to restore)")


def _is_a_directory(path: pathlib.Path) -> bool:
    """Whether a directory is there. What is not there (a name nothing answers to, a file, a link to nothing or one that
    loops) is not; a refusal to look is not its absence."""
    try:
        return stat.S_ISDIR(os.stat(path).st_mode)
    except OSError as e:
        return not not_there(e)
    except ValueError:      # a name with a NUL byte names no file
        return False


def _predecessor(run_dir: pathlib.Path) -> tuple[pathlib.Path | None, str | None]:
    """(the run `run_dir` continues, why that cannot be told). A record that reads and names no predecessor says the run
    continued nothing; so does one that reads while the other is damaged (RUN.started.json is written before anything
    else and names the predecessor the run was given). A record that is there and cannot be read, is not text, is no
    object, or names its predecessor by anything but a path — and no other says — is not "continued nothing": what that
    run continued, and what the runs before it spent, is not known (the cause). No record at all: continued nothing."""
    damaged: list[str] = []
    answered = False
    for name in (STARTED, "RUN.json"):
        try:
            text = (run_dir / name).read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            damaged.append(f"{name} is not text ({e.reason})")
            continue
        except OSError as e:
            if not not_there(e):
                damaged.append(f"{name} cannot be read ({type(e).__name__}: {e.strerror or e})")
            elif os.path.lexists(run_dir / name):    # "nothing there" for a link to nothing or one that loops: it is there
                damaged.append(f"{name} is a link that leads nowhere")
            continue
        except ValueError:      # a name with a NUL byte names no file
            continue
        try:
            doc = json.loads(text)
        except ValueError:
            damaged.append(f"{name} is cut or is not JSON")
            continue
        c = doc.get("continues") if isinstance(doc, dict) else None     # a record that is no object names no predecessor
        if isinstance(c, Mapping) and isinstance(c.get("path"), str) and c["path"] and "\0" not in c["path"]:
            return pathlib.Path(c["path"]), None
        if not isinstance(doc, dict):
            damaged.append(f"{name} is not a run record (a JSON object)")
        elif c is not None:
            damaged.append(f"{name} names the run it continues by something that is not a path")
        else:
            answered = True
    return None, (None if answered else "; ".join(damaged) or None)


def predecessor_of(run_dir: pathlib.Path) -> pathlib.Path | None:
    return _predecessor(run_dir)[0]


def lineage_account(predecessor: pathlib.Path, child: pathlib.Path | None = None) -> dict:
    """What the lineage ending at `predecessor` spent: every run of it once, and every child a superseded claim names
    (its preflight may have spent) but `child` (the run asking). What the readable parts spent is summed — the four
    counters, exact, and `runs` says which part spent what; unknown spend is listed — `unaccounted`, and in it `unread`
    (module docstring) — never counted as 0, and `total` is None while any is listed: the sums are then what is known,
    not the lineage's total.
    A part the lineage cannot name — the run a record continues when the record cannot be read, the run a claim names
    when the claim cannot be read — is `unread`, as is evidence there that does not read: no account passes it over."""
    def key(p) -> str:      # a claim names a run absolute; a caller may give one relative (`--verify --out run3`)
        return os.path.realpath(p)      # not `Path.resolve`: on 3.11-3.12 it raises RuntimeError for a link that loops

    def unknown(holder: dict, text: str) -> None:
        holder["unaccounted"].append(text)
        holder["unread"].append(text)
        holder["exact"] = False

    def add(path: pathlib.Path, **extra) -> dict:
        """The account of a run of the chain: the predecessor asked for, and each run a record names as the one it
        continues. It existed — `aisef run --parent` refuses a parent with no run record — so a directory that is not
        there, is a file, or is a link that leads nowhere is evidence gone, not a run that spent nothing: unknown. (A
        superseded child a claim names is not asked: a claim whose child's directory is not there is UNBEGUN, as the claim
        lifecycle has always decided it, and it spent nothing there.)"""
        runs.append(account_of(path) | extra)
        if not extra and not _is_a_directory(path):
            unknown(runs[-1], f"{path.name}: the lineage names this run and its directory is not there (missing, a file "
                              "or a link that leads nowhere): what it spent is unknown, not 0")
        return runs[-1]

    def listed(where: pathlib.Path, holder: dict) -> list:
        """The claims on `where`; a directory that cannot be listed hides the runs it superseded: what they spent is
        unknown, listed on `holder`'s account — never raised out of the account, never a known 0."""
        try:
            return claims(where)
        except LineageRefused as e:
            unknown(holder, f"{e}: what the runs it superseded spent is unknown")
            return []

    def sibling_of(path: pathlib.Path, holder: dict) -> str | None:
        """The run a claim file names. A claim that names none (an object without `run`) is a claim of nothing; one that
        cannot be read names a run that is not known: its spend is unknown, listed — not passed over."""
        try:
            return _claimed_run(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            unknown(holder, f"{path.parent.name}/{path.name} cannot be read ({type(e).__name__}): the run it names, "
                            "and what that run spent, is unknown")
            return None

    runs, seen, at = [], {key(child)} if child is not None else set(), predecessor
    while at is not None and key(at) not in seen:
        seen.add(key(at))
        add(at)
        nxt, why = _predecessor(at)
        if why:     # the walk ends here because the record cannot say what comes next, not because nothing does
            unknown(runs[-1], f"{at.name}: {why}: what it continued, and what the runs before it spent, is unknown")
        holder = runs[-1]
        for _, path in listed(nxt, holder) if nxt is not None else []:
            sibling = sibling_of(path, holder)
            if sibling and key(sibling) not in seen:
                seen.add(key(sibling))
                add(pathlib.Path(sibling), superseded=True)
        at = nxt
    holder = runs[0] if runs else {"unaccounted": [], "unread": []}
    for _, path in listed(predecessor, holder):     # siblings of `child`: superseded
        sibling = sibling_of(path, holder)
        if sibling and key(sibling) not in seen:
            seen.add(key(sibling))
            add(pathlib.Path(sibling), superseded=True)
    unaccounted = [u for r in runs for u in r["unaccounted"]]
    known = {k: sum(r[k] for r in runs) for k in SPEND}
    return {"runs": runs, **known, "unaccounted": unaccounted, "unread": [u for r in runs for u in r["unread"]],
            "total": None if unaccounted else dict(known)}


def unread_runs(account: Mapping) -> str:
    """The run directories of a lineage account whose evidence does not read, or is gone — where the operator restores it
    (the entries of `unread` name a run by its basename: two runs of a lineage may both be called `out`)."""
    return ", ".join(dict.fromkeys(r["run"] for r in account["runs"] if r["unread"])) or "the runs named below"


def usage_lineage(predecessor: pathlib.Path, child: pathlib.Path, own: Mapping, prices: Mapping | None) -> dict:
    """Tokens and money over the lineage of `child` (this run): every run once (as `lineage_account`), this run's own
    last; a total whose any part is unknown is `null`, never a partial sum shown as the whole. Each run's entry holds
    what that run's readable evidence shows (`cost.known`, `tokens`), attributed; `tokens` is their sum and
    `tokens_status` says whether it is the lineage's total or only what is known."""
    from aisef2.app import usage
    account = lineage_account(predecessor, child)
    entries, blind = [], False
    for acct in account["runs"]:
        d = pathlib.Path(acct["run"])
        try:
            got = events_of(d)
            u = usage.usage(d, [{"seq": e.seq, "type": e.type, "data": dict(e.data)} for e in (got[0] if got else [])],
                            prices, {})
        except Exception as e:  # noqa: BLE001 — a stream the reader refuses: this run's cost is unknown; the others' stay
            blind = True
            entries.append({"run": acct["run"], "recorded": acct["recorded"], "superseded": bool(acct.get("superseded")),
                            "tokens": {}, "cost": {"value": None, "status": "unknown: its evidence cannot be read "
                                                   f"({type(e).__name__}: {getattr(e, 'strerror', None) or e})"[:300]}})
            continue
        cost = dict(u["cost"])
        if (acct["unaccounted"] or not acct["recorded"]) and cost.get("value") is not None:
            cost = {**cost, "value": None, "status": "partial: " + ("; ".join(acct["unaccounted"])[:300] or
                                                                     "the run has no record: its last step may be missing")}
        entries.append({"run": acct["run"], "recorded": acct["recorded"], "superseded": bool(acct.get("superseded")),
                        "tokens": u["tokens"], "cost": cost})
    entries.append({"run": "this run", "recorded": True, "superseded": False, "tokens": dict(own.get("tokens") or {}),
                    "cost": dict(own.get("cost") or {})})
    values = [(e["cost"] or {}).get("value") for e in entries]
    known = all(isinstance(v, (int, float)) for v in values)
    # the runs before this one: whatever their sessions lack is listed in their account (`unaccounted`); this run's own
    # sessions are outside it
    own_blind = any(x.get("steps_without_tokens") or not x.get("steps") for x in own.get("sessions") or [])
    exact = not blind and not any(a["unaccounted"] for a in account["runs"]) and not own_blind \
        and all(e["recorded"] for e in entries)
    return {"runs": entries, "tokens": {k: sum(int(e["tokens"].get(k, 0)) for e in entries) for k in usage.CLASSES},
            "tokens_status": "known" if exact else "lower bound: some run's spend is unknown (not 0)",
            "cost": {"value": round(sum(values), 6) if known else None,
                     "status": "known" if known else "unknown: some run's cost is not known (not 0)"}}


# ------------------------------------------------------------------------------------------------ the anchor's file

ANCHOR_LINE = re.compile(r"[0-9a-f]{64}\n")


def write_anchor(path: pathlib.Path, anchor: str) -> None:
    """The anchor into a NEW file: created exclusively and never through a symbolic link, read-only, exactly one line of
    64 hex digits and a newline, flushed to disk. A write that does not complete leaves a file `read_anchor` refuses —
    never one it accepts."""
    if not re.fullmatch(r"[0-9a-f]{64}", anchor or ""):
        raise ValueError(f"not an evidence anchor: {anchor!r}")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o444)
    with os.fdopen(fd, "wb") as f:
        f.write((anchor + "\n").encode("ascii"))
        f.flush()
        os.fsync(f.fileno())


def read_anchor(path: pathlib.Path) -> str:
    """The anchor a file written by `write_anchor` holds; anything else — short, extended, not hex — is refused."""
    text = pathlib.Path(path).read_bytes().decode("ascii", errors="replace")
    if not ANCHOR_LINE.fullmatch(text):
        raise ValueError(f"{path} is not a complete evidence anchor file")
    return text[:64]
