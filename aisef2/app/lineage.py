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
| BEGUN (its journal holds an event) | — | refused: the lineage continues from the child — never a fork |
| ENDED_UNBEGUN (a record, no journal: refused before it began) | done | superseded: a new generation records the evidence |
| UNBEGUN (no record, no journal) | provably gone (same host, the pid absent or another process) | superseded, with the evidence |
| UNBEGUN | alive, on another host, or not decidable | refused; the operator may supersede by naming the claim's sha256 (recorded as their assertion) |

Nothing is deleted: a superseded claim stays, the new generation points at it. A child that began is never superseded,
by evidence or by assertion. The claim is taken before the run's first provider request, so a run that loses the race
spends nothing.

**Spend.** `account_of` re-derives a run's spend from its evidence alone (the Budget's rules: sessions, journaled
requests, the preflight's ledger) and adds what only the journal shows: a provider request with no result — in flight
when the run ended — whose session stream exists is unknown spend. `lineage_account` sums the lineage (each run once,
and every superseded child, whose preflight may have spent). A continuation of a lineage with unaccounted spend starts
no paid work unless the operator accepts it by name (`--accept-unaccounted`), and the lineage's known spend counts
against the run's ceilings (continuing never resets a budget).

**A file that is damaged, or is not what a run writes** — a ledger line or a claim that is valid JSON and no object, a
session stream the reader refuses — is answered as the torn form of the same file is: unknown spend, listed; the
unreadable-claim marker; a claim passed over, or not superseded without evidence (`LineageRefused`). `claim`,
`continued_by`, `predecessor_of`, `account_of` and `lineage_account` raise nothing else for such a file."""

from __future__ import annotations

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
BEGUN, ENDED_UNBEGUN, UNBEGUN = "BEGUN", "ENDED_UNBEGUN", "UNBEGUN"
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
    """The claim generations on `predecessor`, oldest first."""
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


def child_state(child: pathlib.Path) -> str:
    got = events_of(child) if (child / JOURNAL).exists() else None
    if got is not None and got[0]:
        return BEGUN
    return ENDED_UNBEGUN if (child / "RUN.json").is_file() else UNBEGUN


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
        state = child_state(held) if doc.get("run") else UNBEGUN
        if state == BEGUN:
            raise LineageRefused(f"{predecessor} is continued by {held}, which began: continue the lineage from it")
        gone = True if state == ENDED_UNBEGUN else _gone(doc.get("claimant") or {})
        asserted = supersede is not None and supersede == _sha(data)
        if gone is not True and not asserted:
            why = "is alive" if gone is False else "cannot be shown gone (another host, or its identity unreadable)"
            raise LineageRefused(f"{predecessor} is claimed by {held} ({path.name}), whose claimant {why} and which has "
                                 f"not begun: not superseded without evidence (an operator may name it: "
                                 f"--supersede-claim {_sha(data)})")
        supersedes = {"claim": path.name, "sha256": _sha(data), "child": str(held), "child_state": state,
                      "claimant_gone": gone, "operator_asserted": asserted and gone is not True}
        target = predecessor / f"CONTINUED-BY.{n + 1}.json"
    doc = {"run": str(child), "claimed": at, "claimant": claimant(), **({"supersedes": supersedes} if supersedes else {})}
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o444)
    except FileExistsError:
        raise LineageRefused(f"{predecessor}: another run took {target.name} at the same moment: a run is continued "
                             "once") from None
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
        fields = dict(ln.split(" ", 1) for ln in block.splitlines() if " " in ln)
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

def account_of(run_dir: pathlib.Path) -> dict:
    """What `run_dir` spent, re-derived from its evidence (the run's Budget rules), and what is unknown."""
    from aisef2.app import client, preflight
    got = events_of(run_dir)
    events = got[0] if got else []
    requests = [e for e in events if e.type == "provider/request"]
    answered = {s for e in events if e.type == "provider/result" for s in e.source_seqs}
    try:
        pre = preflight.accounting(run_dir / "preflight" / "LEDGER.jsonl")
    except Exception:  # noqa: BLE001 — a ledger the reader refuses, whatever its damage, is spend that is unknown
        pre = {k: 0 for k in SPEND} | {"unaccounted": ["the preflight's ledger does not read"]}
    huge = {k: 10 ** 12 for k in SPEND}
    try:
        spent = client.Budget(huge, pre, run_dir / "sessions", lambda: len(requests)).spend()
    except Exception as e:  # noqa: BLE001 — a stream the reader refuses: what the sessions spent is unknown, not 0
        spent = {**{k: pre[k] for k in SPEND}, "provider_requests": pre["provider_requests"] + len(requests),
                 "unaccounted": [f"{run_dir.name}: a session's event stream does not read ({type(e).__name__}): what "
                                 "the sessions spent is unknown"]}
    unaccounted = list(spent["unaccounted"]) + [f"preflight request {n} sent and never answered" for n in pre.get("unaccounted") or []]
    logs = [p.name for p in (run_dir / "sessions").glob("*.jsonl")] if (run_dir / "sessions").is_dir() else []
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
    return {"run": str(run_dir), "recorded": (run_dir / "RUN.json").is_file(),
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
    runs, seen, at = [], {key(child)} if child is not None else set(), predecessor
    while at is not None and key(at) not in seen:
        seen.add(key(at))
        runs.append(account_of(at))
        nxt = predecessor_of(at)
        for _, path in claims(nxt) if nxt is not None else []:
            try:
                sibling = _claimed_run(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                sibling = None
            if sibling and key(sibling) not in seen:
                seen.add(key(sibling))
                runs.append(account_of(pathlib.Path(sibling)) | {"superseded": True})
        at = nxt
    for _, path in claims(predecessor):     # siblings of `child`: superseded children of the predecessor itself
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
