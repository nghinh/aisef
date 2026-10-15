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
| ENDED_UNBEGUN (a record, no journal: refused before it began) | done | superseded: a new generation records the evidence |
| UNBEGUN (no record, no journal, or a journal of no bytes) | provably gone (same host, the pid absent or another process) | superseded, with the evidence |
| UNBEGUN | alive, on another host, or not decidable | refused; the operator may supersede by naming the claim's sha256 (recorded as their assertion) |
| UNREAD (evidence there that cannot be read: see below) | whatever it is | refused; only the operator's sha256 supersedes (recorded as their assertion, with the cause) |

Nothing is deleted: a superseded claim stays, the new generation points at it. A child whose journal reads and holds an
event began and is never superseded, by evidence or by assertion. **A child whose evidence is there and cannot be read
is not one that did not begin** (it is UNREAD, never UNBEGUN): a directory the system will not let this process search,
a journal it will not open, one that does not reconstruct, one that holds bytes and no complete event. That the
evidence of the beginning is damaged says nothing about whether the child began, and the claimant's absence is evidence
about a process, not about the child's run; so no evidence supersedes it — and a failure to read releases and takes
nothing. What is genuinely not there is still not evidence of a beginning. The claim is taken before the run's first
provider request, so a run that loses the race spends nothing.

**A predecessor this process may not list, search or write** is a refusal (`LineageRefused`, which `aisef run` answers
with exit 2 and `aisef bundle continue` with `refused:`), never a traceback and never "no claims": the generations of
a directory whose listing is denied cannot be told, and the newest decides.

**Spend.** `account_of` re-derives a run's spend from its evidence alone (the Budget's rules: sessions, journaled
requests, the preflight's ledger) and adds what only the journal shows: a provider request with no result — in flight
when the run ended — whose session stream exists is unknown spend. `lineage_account` sums the lineage (each run once,
and every superseded child, whose preflight may have spent). A continuation of a lineage with unaccounted spend starts
no paid work unless the operator accepts it by name (`--accept-unaccounted`), and the lineage's known spend counts
against the run's ceilings (continuing never resets a budget). Evidence the system will not let `account_of` look at — a
run directory with no search permission, a `sessions` that is a link into a directory that cannot be traversed or is a
directory that cannot be listed — is unknown spend, listed: never raised out of it, never a 0 shown as known. What is
genuinely not there (no sessions directory, no ledger, no run directory) is not unknown: it is what a run that spent
nothing there looks like.

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
    if not isinstance(doc, dict) or not isinstance(doc.get("run", ""), str):
        raise ValueError("not a claim")
    return doc.get("run")


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
    out = [(1, predecessor / CLAIM)] if (predecessor / CLAIM).exists() else []
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
    event (a first line that was cut). Else the evidence is not there: ENDED_UNBEGUN (a record: it was refused before it
    began) or UNBEGUN (nothing, or a journal of no bytes)."""
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
        text = None
    if text:
        try:
            events = format3.reconstruct(text).events
        except Exception as e:  # noqa: BLE001 — a journal the reader refuses is evidence that cannot be read, not none
            return UNREAD, f"{JOURNAL.name} does not reconstruct ({type(e).__name__}: {e})"[:300]
        if events:
            return BEGUN, None
        return UNREAD, f"{JOURNAL.name} holds bytes and no complete event (a first line that was cut)"
    return (ENDED_UNBEGUN if (child / "RUN.json").is_file() else UNBEGUN), None


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
    return p.stdout.strip() or None


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
                                 f"({type(e).__name__}): not superseded without evidence") from None
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
                                 f"--supersede-claim {_sha(data)}")
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
        raise LineageRefused(f"{predecessor} cannot be claimed: {target.name} cannot be created ({type(e).__name__}: "
                             f"{e.strerror or e}) — the claim is a file in that directory: restore write access to it "
                             "(or continue a writable copy of the run, which is then the run that is claimed); nothing "
                             "was taken") from None
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
        return "(an unreadable claim)", None
    return run, child_state(pathlib.Path(run)) if run else None


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
    """What `run_dir` spent, re-derived from its evidence (the run's Budget rules), and what is unknown."""
    from aisef2.app import client, preflight
    got = events_of(run_dir)
    events = got[0] if got else []
    requests = [e for e in events if e.type == "provider/request"]
    answered = {s for e in events if e.type == "provider/result" for s in e.source_seqs}
    ledger, sessions = run_dir / "preflight" / "LEDGER.jsonl", run_dir / "sessions"
    try:
        _look(ledger)
        pre = preflight.accounting(ledger)
    except Exception:  # noqa: BLE001 — a ledger the reader refuses, whatever its damage, is spend that is unknown
        pre = {k: 0 for k in SPEND} | {"unaccounted": ["the preflight's ledger does not read"]}
    huge = {k: 10 ** 12 for k in SPEND}
    try:
        _look(sessions)
        spent = client.Budget(huge, pre, sessions, lambda: len(requests)).spend()
    except Exception as e:  # noqa: BLE001 — a stream the reader refuses: what the sessions spent is unknown, not 0
        spent = {**{k: pre[k] for k in SPEND}, "provider_requests": pre["provider_requests"] + len(requests),
                 "unaccounted": [f"{run_dir.name}: a session's event stream does not read ({type(e).__name__}): what "
                                 "the sessions spent is unknown"]}
    unaccounted = list(spent["unaccounted"]) + [f"preflight request {n} sent and never answered" for n in pre.get("unaccounted") or []]
    logs = [p.name for p in sessions.glob("*.jsonl")] if os.path.isdir(sessions) else []
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
    return {"run": str(run_dir), "recorded": os.path.isfile(run_dir / "RUN.json"),
            **{k: int(spent[k]) for k in SPEND}, "unaccounted": unaccounted}


def predecessor_of(run_dir: pathlib.Path) -> pathlib.Path | None:
    for name in (STARTED, "RUN.json"):
        try:
            doc = json.loads((run_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        c = doc.get("continues") if isinstance(doc, dict) else None     # a record that is no object names no predecessor
        if isinstance(c, Mapping) and isinstance(c.get("path"), str) and c["path"]:
            return pathlib.Path(c["path"])
    return None


def lineage_account(predecessor: pathlib.Path, child: pathlib.Path | None = None) -> dict:
    """What the lineage ending at `predecessor` spent: every run of it once, and every child a superseded claim names
    (its preflight may have spent) but `child` (the run asking). Unknown spend is listed, never counted as 0."""
    def key(p) -> str:      # a claim names a run absolute; a caller may give one relative (`--verify --out run3`)
        return str(pathlib.Path(p).resolve())
    def listed(where: pathlib.Path, holder: dict) -> list:
        """The claims on `where`; a directory that cannot be listed hides the runs it superseded: what they spent is
        unknown, listed on `holder`'s account — never raised out of the account, never a known 0."""
        try:
            return claims(where)
        except LineageRefused as e:
            holder["unaccounted"].append(f"{e}: what the runs it superseded spent is unknown")
            return []

    runs, seen, at = [], {key(child)} if child is not None else set(), predecessor
    while at is not None and key(at) not in seen:
        seen.add(key(at))
        runs.append(account_of(at))
        nxt = predecessor_of(at)
        for _, path in listed(nxt, runs[-1]) if nxt is not None else []:
            try:
                sibling = _claimed_run(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                sibling = None
            if sibling and key(sibling) not in seen:
                seen.add(key(sibling))
                runs.append(account_of(pathlib.Path(sibling)) | {"superseded": True})
        at = nxt
    for _, path in listed(predecessor, runs[0] if runs else {"unaccounted": []}):     # siblings of `child`: superseded
        try:
            sibling = _claimed_run(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if sibling and key(sibling) not in seen:
            seen.add(key(sibling))
            runs.append(account_of(pathlib.Path(sibling)) | {"superseded": True})
    return {"runs": runs, **{k: sum(r[k] for r in runs) for k in SPEND},
            "unaccounted": [u for r in runs for u in r["unaccounted"]]}


def usage_lineage(predecessor: pathlib.Path, child: pathlib.Path, own: Mapping, prices: Mapping | None) -> dict:
    """Tokens and money over the lineage of `child` (this run): every run once (as `lineage_account`), this run's own
    last; a total whose any part is unknown is `null`, never a partial sum shown as the whole."""
    from aisef2.app import usage
    entries = []
    for acct in lineage_account(predecessor, child)["runs"]:
        d = pathlib.Path(acct["run"])
        got = events_of(d)
        u = usage.usage(d, [{"seq": e.seq, "type": e.type, "data": dict(e.data)} for e in (got[0] if got else [])],
                        prices, {})
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
    return {"runs": entries, "tokens": {k: sum(int(e["tokens"].get(k, 0)) for e in entries) for k in usage.CLASSES},
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
