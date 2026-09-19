"""Behavior ledger — VERIFIED / GAP / REOPENED (ADR-004 R2, R6, R7).

The story gate answers "is this story done". It **cannot** answer the second
question, the one HoH measured at 17/81 issues reopened: *which behavior was
once correct then broke?* Today's evidence is sufficient to answer — each test
run records every test name and which ones are red, each mockup comparison
records which screens match — but no one reads it **over time**.

This module is a **projection**, not a new store: there is no event only it
records, no fact only it knows. Deleting `ledger.json` and rebuilding from
`evidence/` must produce the same result — except `loops[]`, the improvement
loop milestones, the only part not derivable from evidence and therefore
carried over from the old ledger. Hence no one can edit behavior history,
and there is no place for someone to "mark as done".

Four behavior kinds, each from a machine-readable source:

* `AC-<story>-<i>` — test name from `tool_run test` (via `acceptance`);
* `FR-x` / `NFR-x` — story's `covers`, green when story criteria are green;
* `qa:<kind>`   — `tool_run` named `qa:<kind>`;
* `mockup:<screen>` — `mockup_map` event.

Status inferred by code in chronological order, no one declares:

    (none) -> green  -> VERIFIED
    (none) -> red    -> GAP
    VERIFIED  -> red -> REOPENED  (`regressed_by` = story#attempt[@candidate])
    GAP/REOPENED -> green -> VERIFIED  (counted as *resolved*)

History records only state **changes**. e9 has ~100 test runs x ~280 test
names; recording every observation would make the ledger larger than the
evidence it projects.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.observe import (
    BEHAVIOR,
    EVIDENCE_DIR,
    MOCKUP_MAP,
    NOTE,
    TOOL_RUN,
    AGENT_RUN,
    EvidenceStore,
)
from .acceptance import ac_code, coverage as ac_coverage
from .journal import JournalStore

VERSION = 1
#: Human-declared traceability: behavior -> {test_id, why, by, at} (decision B6 2026-09-06).
TRACE_FILE = "traceability.json"
LEDGER_FILE = "ledger.json"
INDEX_FILE = "INDEX.md"
STORIES_INDEX = "stories.index.json"

VERIFIED = "verified"
GAP = "gap"
REOPENED = "reopened"

#: Which **absence** a GAP/REOPENED is (ADR-009 O2). Three different absences used to
#: be recorded as the same GAP, and only the first deserves a paid repair story — the
#: owner decision of 2026-09-06 §4 ("a gap that is only missing traceability is fixed
#: by the harness, not by a story") lived in prose until now.
UNBUILT = "unbuilt"      # nothing landed proves the behaviour: red test, unlanded green, red check
UNTESTED = "untested"    # the run was readable and no test name carries this code
UNTRACED = "untraced"    # the harness cannot link behaviour -> test: metadata fix, not a story

#: The exact `source.why` sentences the ledger itself writes. `gap_kind` reads them
#: back, so writer and reader cannot drift apart into two different vocabularies.
WHY_NO_TEST = "no test carries this code"
WHY_UNREADABLE = "cannot read test names from runner output"
WHY_TRACE_ABSENT = "declared trace not in this run"
#: SS-88: the criterion's tests were collected but skipped or errored. Deliberately not UNTESTED/UNTRACED — a test
#: that stopped executing can hide a real regression, so `gap_kind` leaves it on the expensive side (UNBUILT).
WHY_NOT_EXECUTED = "its tests did not execute (skipped or errored)"
WHY_UNLANDED = "green on unlanded candidate — attempt not yet gated/merged"

#: Columns of the gap/regression table (R12) — Markdown and CSV use the same
#: order, so the human-readable and machine-readable files tell the same story.
#: `gap_kind` is appended, never inserted: a tracker importing the CSV by position
#: keeps reading the same columns it read before.
ISSUE_COLUMNS = ("id", "kind", "status", "story", "regressed_by", "source", "why",
                 "candidate", "since", "changes", "gap_kind")

#: Evidence not belonging to any story — planning phase, mockup building, skill scan.
PHASE_PREFIXES = ("plan-", "mockup-", "skill-")
#: Project-level evidence of improvement loops (ADR-004 R3): `evidence/loop-<n>.jsonl`.
#: A **milestone**, not a story: the ledger reads it (behaviors have `since = loop-n`)
#: but does not build an index line for it.
LOOP_PREFIX = "loop-"

_ATTEMPT = re.compile(r"#(\d+)$")
_EPIC_FROM_ID = re.compile(r"^STORY-(\d+)-")


@dataclass
class Behavior:
    """A behavior and its full lifecycle."""

    id: str
    kind: str                                   # ac | fr | nfr | qa | mockup
    story: str = ""
    status: str = ""
    candidate: str = ""
    since: str = ""                             # "<story>#<attempt>" or "loop-n"
    source: dict = field(default_factory=dict)
    regressed_by: str = ""
    history: list[dict] = field(default_factory=list)

    @property
    def ever_verified(self) -> bool:
        return any(h["status"] == VERIFIED for h in self.history)

    @property
    def gap_kind(self) -> str:
        """Which absence this GAP/REOPENED is (ADR-009 O2); empty when VERIFIED.

        Read off `source.why` and nothing else, so the kind stays a **projection**
        like the rest of this module: `_observe_tests` writes exactly one of the
        `WHY_*` sentences, and every other cause (red test, green on an unlanded
        candidate, project check red, missing screen) means nothing landed proves
        the behaviour. Unknown therefore defaults to `UNBUILT` on purpose —
        mislabelling a real defect as a cheap harness fix would hide it, the
        reverse only wastes money.
        """
        if self.status in ("", VERIFIED):
            return ""
        why = str((self.source or {}).get("why") or "")
        if why.startswith((WHY_UNREADABLE, WHY_TRACE_ABSENT)):
            return UNTRACED
        return UNTESTED if why == WHY_NO_TEST else UNBUILT

    def as_dict(self) -> dict:
        out = {
            "kind": self.kind, "status": self.status, "candidate": self.candidate,
            "since": self.since, "source": self.source, "history": self.history,
        }
        if self.gap_kind:
            out["gap_kind"] = self.gap_kind
        if self.story:
            out["story"] = self.story
        if self.regressed_by:
            out["regressed_by"] = self.regressed_by
        return out


@dataclass
class StoryLine:
    """An index line: enough to decide whether evidence needs reading."""

    id: str
    epic: str = ""
    acceptance: int = 0
    covers: list[str] = field(default_factory=list)
    status: str = "?"
    candidate: str = ""

    @property
    def evidence_path(self) -> str:
        return f"{EVIDENCE_DIR}/{self.id}.jsonl"


@dataclass
class Ledger:
    root: Path = field(default_factory=Path)
    behaviors: dict[str, Behavior] = field(default_factory=dict)
    stories: dict[str, StoryLine] = field(default_factory=dict)
    loops: list[dict] = field(default_factory=list)
    #: Number of times a verified behavior was broken again, and gaps resolved.
    reopen_events: int = 0
    resolved: int = 0
    #: **Cross-story** regressions: behavior green in story A, red again in
    #: evidence of story B != A. This is the number HoH measured (17/81 for
    #: Fusepoint); red-again within the story's own turn is mostly normal TDD,
    #: not regression.
    cross_reopens: list[dict] = field(default_factory=list)
    #: Green results on **unlanded** candidates (attempts not yet gated/merged)
    #: are discarded, not counted as VERIFIED. Measured 2026-09-06 (R3, fake
    #: client): story fix attempt failed the gate — test green in worktree,
    #: reviewer blocked — yet it made the original behavior VERIFIED despite
    #: nothing reaching the main branch.
    unlanded_green: int = 0
    #: Human-declared traceability (`aisef evidence <AC> --link`): behavior ->
    #: test that proves it. Only a **test name**: the ledger still requires that
    #: test to be green on a landed candidate, no one can write VERIFIED directly.
    links: dict[str, dict] = field(default_factory=dict)

    # ------------------------------------------------------------- recording

    def observe(
        self,
        bid: str,
        kind: str,
        *,
        ok: bool,
        at: float,
        story: str,
        owner: str = "",
        attempt: int = 0,
        candidate: str = "",
        source: dict | None = None,
        landed: bool = True,
    ) -> None:
        """Record one observation.

        `story` is the **observing** story (which evidence file records it),
        `owner` is the story that **owns** the behavior. The two differ at
        the most interesting moment: a prior story's criterion goes red during
        a later story's run.
        """
        if ok and not landed:
            # Green on unlanded candidate is not "verified": that code may
            # never land. Red still counts — do not trust the client.
            self.unlanded_green += 1
            if bid in self.behaviors:
                return
            ok = False
            source = {**(source or {}), "why": WHY_UNLANDED}
        b = self.behaviors.get(bid)
        if b is None:
            b = self.behaviors[bid] = Behavior(id=bid, kind=kind)
        b.story = b.story or owner or story

        status = VERIFIED if ok else (REOPENED if b.ever_verified else GAP)
        if status == b.status:
            # No state change: update the latest candidate, do not record history.
            b.candidate = candidate or b.candidate
            # The **reason** of a non-green behaviour must not go stale: `gap_kind`
            # routes repair money by it (ADR-009 O2), and a gap first seen as "no
            # test carries this code" that a later run shows as a *red test* is a
            # different absence with a different fix. VERIFIED keeps its source —
            # the run that proved it is the one worth naming.
            if status != VERIFIED:
                b.source = dict(source or {})
            return

        marker = f"{story}#{attempt}" if attempt else story
        if status == REOPENED:
            self.reopen_events += 1
            b.regressed_by = marker + (f"@{candidate[:7]}" if candidate else "")
            was = next(
                (h["story"] for h in reversed(b.history) if h["status"] == VERIFIED), ""
            )
            if was and was != story:
                self.cross_reopens.append(
                    {"id": bid, "verified_by": was, "regressed_by": b.regressed_by, "at": at}
                )
        elif status == VERIFIED and b.status in (GAP, REOPENED):
            self.resolved += 1
            b.regressed_by = ""

        b.status, b.candidate, b.since = status, candidate, marker
        b.source = dict(source or {})
        b.history.append({
            "at": at, "status": status, "candidate": candidate,
            "story": story, "source": b.source,
        })

    # ------------------------------------------------------------- queries

    def summary(self) -> dict:
        counts = {VERIFIED: 0, GAP: 0, REOPENED: 0}
        for b in self.behaviors.values():
            counts[b.status] = counts.get(b.status, 0) + 1
        return {
            "behaviors": len(self.behaviors),
            "verified": counts[VERIFIED],
            "gap": counts[GAP],
            "reopened": counts[REOPENED],
            "resolved": self.resolved,
            "reopen_events": self.reopen_events,
            "cross_reopens": len(self.cross_reopens),
            "unlanded_green": self.unlanded_green,
            # The three absences (ADR-009 O2) counted over **every** non-green
            # behaviour, so they add up to `gap + reopened` -- not to `gap`.
            "gap_kinds": gap_kind_counts(self.issues()),
        }

    def epic_of(self, story_id: str) -> str:
        line = self.stories.get(story_id)
        return (line.epic if line else "") or _epic_of(story_id)

    def for_story(self, story_id: str) -> list[Behavior]:
        """Behaviors *of* a story: its criteria and requirements it covers,
        plus behaviors whose state was first set by its own evidence."""
        line = self.stories.get(story_id)
        ids = set()
        if line:
            ids |= {ac_code(story_id, i) for i in range(1, line.acceptance + 1)}
            ids |= set(line.covers)
        return [
            b for b in self.behaviors.values()
            if b.id in ids or b.story == story_id
        ]

    def counts_for(self, story_id: str) -> tuple[int, int, int]:
        out = {VERIFIED: 0, GAP: 0, REOPENED: 0}
        for b in self.for_story(story_id):
            out[b.status] = out.get(b.status, 0) + 1
        return out[VERIFIED], out[GAP], out[REOPENED]

    def metrics(self) -> dict:
        """R7 — four improvement loop numbers, all read from `history`."""
        entries = sorted(
            ((h["at"], bid, h) for bid, b in self.behaviors.items() for h in b.history),
            key=lambda t: (t[0], t[1]),
        )
        seen: set[str] = set()
        growth: list[dict] = []
        for at, bid, h in entries:
            if h["status"] == VERIFIED and bid not in seen:
                seen.add(bid)
                growth.append({"at": at, "story": h.get("story", ""), "verified": len(seen)})

        s = self.summary()
        loops = []
        prev = None
        for loop in self.loops:
            dv = loop["verified"] - (prev["verified"] if prev else 0)
            dr = loop["reopened"] - (prev["reopened"] if prev else 0)
            cost = float(loop.get("cost_usd") or 0.0)
            loops.append({
                **loop,
                "d_verified": dv,
                "d_reopened": dr,
                # Marginal improvement: net behaviors gained per dollar that loop.
                # No cost means no denominator — `None`, not 0.
                "marginal": ((dv - dr) / cost) if cost else None,
            })
            prev = loop
        return {
            **s,
            "ever_verified": len(seen),
            "growth": growth,
            "reopen_rate": (self.reopen_events / len(seen)) if seen else 0.0,
            "cross_reopen_list": self.cross_reopens,
            "loops": loops,
        }

    def issues(self, *, epic: str = "", statuses=(GAP, REOPENED)) -> list[dict]:
        """R12 — one row per non-green behavior, for tracking outside the repo.

        Regressions first: "was correct then broke" is what the reader of this
        table needs to see first; gaps are already reported by the story gate.
        `changes` is the number of state transitions — a behavior that flips
        back and forth many times signals stories stepping on each other,
        not derivable from current status alone.
        """
        want = set(statuses)
        rows = []
        for b in sorted(self.behaviors.values(),
                        key=lambda b: (b.status != REOPENED, b.story, b.id)):
            if b.status not in want or (epic and self.epic_of(b.story) != epic):
                continue
            src = b.source
            rows.append({
                "id": b.id, "kind": b.kind, "status": b.status, "story": b.story,
                "regressed_by": b.regressed_by,
                "source": str(src.get("test_id") or src.get("screen")
                              or (f"qa:{src['qa_kind']}" if src.get("qa_kind") else "")),
                "why": str(src.get("why") or ""),
                "candidate": b.candidate[:7], "since": b.since, "changes": len(b.history),
                "gap_kind": b.gap_kind,
            })
        return rows

    def snapshot(self, loop_label: str, cost_usd: float = 0.0) -> dict:
        """Record a milestone (improvement loop or run) into `loops[]`."""
        s = self.summary()
        rec = {
            "n": loop_label, "at": time.time(),
            "verified": s["verified"], "gap": s["gap"], "reopened": s["reopened"],
            "cost_usd": float(cost_usd),
        }
        self.loops.append(rec)
        return rec

    # ------------------------------------------------------------- persist

    def as_dict(self) -> dict:
        return {
            "version": VERSION,
            "behaviors": {bid: b.as_dict() for bid, b in sorted(self.behaviors.items())},
            "loops": self.loops,
        }

    def write(self, root: Path | str | None = None) -> Path:
        path = Path(root or self.root) / LEDGER_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------- index

    def index_lines(self) -> list[str]:
        """R6 — one line per epic, one line per story. Nothing more.

        The index *replaces* dumping history into the prompt: it says what
        exists and where; anyone needing details uses `aisef evidence <id>`.
        """
        by_epic: dict[str, list[StoryLine]] = {}
        for line in self.stories.values():
            by_epic.setdefault(self.epic_of(line.id), []).append(line)
        out: list[str] = []
        for epic in sorted(by_epic):
            stories = sorted(by_epic[epic], key=lambda s: s.id)
            tv = tg = tr = 0
            body = []
            for s in stories:
                v, g, r = self.counts_for(s.id)
                tv, tg, tr = tv + v, tg + g, tr + r
                body.append(
                    f"- {s.id} · {s.status} · {s.candidate[:7] or '—'} · "
                    f"V{v} G{g} R{r} · {s.evidence_path}"
                )
            done = sum(1 for s in stories if s.status == "done")
            out.append(f"## {epic} — {done}/{len(stories)} stories done · V{tv} G{tg} R{tr}")
            out += body
        return out

    def index(self, root: Path | str | None = None) -> Path:
        text = "\n".join([
            "# Evidence index",
            "",
            "One line per story: status · candidate · behaviour count "
            "VERIFIED/GAP/REOPENED · evidence file. Details: `aisef evidence <id>`.",
            "",
            *self.index_lines(),
        ]) + "\n"
        path = Path(root or self.root) / INDEX_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def epic_slice(self, epic_id: str, *, max_chars: int = 2000) -> str:
        """Index slice for one epic, for a prompt slot. Capped: context is a
        finite resource, and truncation with notice beats silent overflow."""
        want = epic_id or ""
        keep: list[str] = []
        taking = False
        for line in self.index_lines():
            if line.startswith("## "):
                taking = line[3:].split(" —")[0].strip() == want
            if taking:
                keep.append(line)
        text = "\n".join(keep)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n_(truncated to character limit — `aisef evidence <id>`)_"
        return text


def gap_kind_counts(rows: list[dict]) -> dict:
    """The three absences counted apart (ADR-009 O2) — always all three keys, so a
    zero reads as "measured zero", not as "not reported"."""
    return {k: sum(1 for r in rows if r.get("gap_kind") == k)
            for k in (UNBUILT, UNTESTED, UNTRACED)}


def issues_text(rows: list[dict], fmt: str) -> str:
    """R12 table as Markdown or standard CSV (`csv`, importable by any tracker)."""
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=ISSUE_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()
    cell = lambda v: str(v).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    c = gap_kind_counts(rows)
    return "\n".join([
        f"# Gap / regression · {len(rows)} behaviours · "
        f"unbuilt {c[UNBUILT]} · untested {c[UNTESTED]} · untraced {c[UNTRACED]}",
        "",
        "| " + " | ".join(ISSUE_COLUMNS) + " |",
        "|" + "---|" * len(ISSUE_COLUMNS),
        *("| " + " | ".join(cell(r[c]) for c in ISSUE_COLUMNS) + " |" for r in rows),
    ]) + "\n"


# ---------------------------------------------------------------- build


def build(artifact_root: Path | str) -> Ledger:
    """Project all of `evidence/` into a behavior ledger, in chronological order."""
    root = Path(artifact_root)
    led = Ledger(root=root)

    index = _read_json(root / STORIES_INDEX)
    for raw in index.get("stories") or []:
        sid = str(raw.get("id") or "")
        if not sid:
            continue
        led.stories[sid] = StoryLine(
            id=sid,
            epic=str(raw.get("epic_id") or ""),
            acceptance=len(raw.get("acceptance_criteria") or []),
            covers=[str(c) for c in raw.get("covers") or []],
        )
    for sid, rec in (_read_json(root / "sprint-status.json").get("stories") or {}).items():
        if sid in led.stories and isinstance(rec, dict):
            led.stories[sid].status = str(rec.get("status") or "?")

    # `behaviors` is rebuilt from scratch every time; `loops[]` is the **only**
    # part not derivable from evidence (milestones and cost of an improvement
    # loop), so it is carried over from the old ledger — otherwise a single
    # `aisef report` would wipe the milestones the R3 loop just recorded.
    led.loops = [lo for lo in _read_json(root / LEDGER_FILE).get("loops") or []
                 if isinstance(lo, dict)]
    led.links = {bid: v for bid, v in _read_json(root / TRACE_FILE).items()
                 if isinstance(v, dict) and v.get("test_id")}

    store = EvidenceStore(root)
    events: list[tuple] = []
    for sid in store.stories():
        if sid.startswith(PHASE_PREFIXES):
            continue
        if not sid.startswith(LOOP_PREFIX):
            led.stories.setdefault(sid, StoryLine(id=sid))
        for e in store.read(sid).events:
            events.append((e.at, sid, e.seq, e))
    # Chronological order **across** stories: `seq` is meaningful only within one file.
    events.sort(key=lambda t: (t[0], t[1], t[2]))

    landed_of = _landed_candidates(root)
    # Passing the gate on a candidate means that candidate is landed at the
    # attempt level (`note gate:verdict ok=True`, written by `implement.run_attempt`):
    # implement does not merge, and stories run via `implement_story` directly
    # have no merge journal.
    for _at, sid, _seq, e in events:
        if e.kind == NOTE and e.name == "gate:verdict" and e.ok and e.detail.get("candidate"):
            landed_of.setdefault(sid, set()).add(str(e.detail["candidate"]))
    attempts: dict[str, int] = {}
    for at, sid, _seq, e in events:
        attempts[sid] = _attempt(e, sid, attempts.get(sid, 0))
        n = attempts[sid]
        # R1 done by another flow; old evidence has no candidate and that is valid.
        cand = str(e.detail.get("candidate") or "")
        # Story has a frozen candidate (R1): only landed SHAs count, and an
        # event **not carrying** its candidate is a mid-session agent run
        # before freezing — green there has not reached the main branch. Bug 26
        # (par B3, 2026-09-06): story failed, not merged, yet 3 of its
        # behaviors were VERIFIED by that exact run. No journal / never frozen
        # (project-level QA, loop milestones, pre-R1 evidence) -> candidate is
        # main branch HEAD, counted as before.
        landed = cand in landed_of[sid] if sid in landed_of else True
        if cand and sid in led.stories:
            led.stories[sid].candidate = cand

        if e.kind == BEHAVIOR:
            det = e.detail
            led.observe(
                str(det.get("id") or e.name), str(det.get("kind") or _kind_of(e.name)),
                ok=str(det.get("status") or "") == VERIFIED, at=at, story=sid,
                attempt=n, candidate=cand or str(det.get("candidate") or ""),
                source=dict(det.get("source") or {}), landed=landed,
            )
        elif e.kind == TOOL_RUN and e.name == "test":
            _observe_tests(led, e, sid, n, cand, at, landed=landed)
        elif e.kind == TOOL_RUN and e.name.startswith("qa:"):
            led.observe(
                e.name, "qa", ok=bool(e.ok) and not e.detail.get("skipped"),
                at=at, story=sid, attempt=n, candidate=cand, landed=landed,
                source={"qa_kind": e.name.split(":", 1)[1],
                        **({"why": str(e.detail["skipped"])} if e.detail.get("skipped") else {})},
            )
        elif e.kind == MOCKUP_MAP:
            missing = list(e.detail.get("missing") or []) + list(e.detail.get("missing_data_roles") or [])
            led.observe(
                f"mockup:{e.name}", "mockup", ok=bool(e.ok), at=at, story=sid,
                attempt=n, candidate=cand, landed=landed,
                source={"screen": e.name, **({"why": "missing " + ", ".join(missing)} if missing else {})},
            )
    return led


def _landed_candidates(root: Path) -> dict[str, set[str]]:
    """Story -> set of landed candidate SHAs, read from the journal (ADR-004 R1).

    A candidate is landed when after freezing it has `merge.completed`, or
    when it is the **last** candidate of a `done`/`verified` story (running
    directly in the project has no merge). `attempt.committed` is **not** a
    success marker — it closes the transaction even when the story fails (e9
    STORY-01-07 2026-09-06: journal ends with `attempt.committed` yet story
    is `failed`). Only stories **with** a journal appear in the map — no
    journal means evidence does not belong to any attempt (project-level QA,
    loop milestones), not "unlanded". Stories with a journal but **never
    frozen** (run before R1) also do not appear in the map — same reason.
    """
    store = JournalStore(root)
    status = {sid: str(rec.get("status") or "")
              for sid, rec in (_read_json(root / "sprint-status.json").get("stories") or {}).items()
              if isinstance(rec, dict)}
    out: dict[str, set[str]] = {}
    for path in sorted(store.root.glob("*.jsonl")):
        sid = path.stem
        cur, landed = "", set()
        for en in store.read(sid).entries:
            if en.step == "candidate.frozen":
                cur = str((en.data or {}).get("sha") or "")
            elif en.step == "merge.completed" and cur:
                landed.add(cur)
        if cur and status.get(sid) in ("done", "verified"):
            landed.add(cur)
        if cur:
            out[sid] = landed
    return out


def _observe_tests(led: Ledger, e, sid: str, attempt: int, cand: str, at: float,
                   *, landed: bool = True) -> None:
    """One test run -> status of every criterion it *sees*.

    The home story is fully scored: a criterion with no test carrying its
    code is GAP, consistent with the gate saying "not configured != passed".
    Other stories are scored only on criteria that actually have tests in
    this run — a partial test suite must not turn unrelated stories into
    regressions.

    A requirement (`covers`) is judged **once per run**, not once per story that
    covers it: several stories may cover the same `FR-x`, and the requirement is
    green when *any* of the stories judged in this run has all its criteria green.
    An absence in a later story's own criteria is recorded where it belongs — on
    that criterion, as UNTESTED — and cannot erase evidence another story just
    left for the same requirement. Measured on todo-cli STORY-06-01: five
    requirements flipped to REOPENED while all 65 tests were green, because that
    story covers what three earlier stories cover and one of its eight criteria
    had no test. Ordering matters for the same reason: `observe` compares events
    by `(at, sid, seq)`, and the order of `targets` *inside* one event is not an
    ordering at all — so the verdicts are aggregated before `observe` sees them,
    instead of letting the last writer of the loop win (it did not: the home
    story wrote red first and the owner's green, arriving after, was dropped by
    the unlanded-candidate early return, which stays as it is).
    """
    det = e.detail
    ids = [str(t) for t in det.get("test_ids") or []]
    failed = {str(t) for t in det.get("failed_ids") or []}
    # SS-88: a skipped or errored criterion test did not execute — it verifies nothing (proof.not_green)
    from .proof import not_green
    unexecuted = not_green(det) - failed
    readable = bool(det.get("test_format")) and bool(ids)

    def note(story_id: str, i: int, ok: bool, source: dict) -> None:
        led.observe(ac_code(story_id, i), "ac", ok=ok, at=at, story=sid,
                    owner=story_id, attempt=attempt, candidate=cand, landed=landed,
                    source={"test_run": e.name, **source})

    # requirement -> (green, why, story it is credited to) for *this* run. Green wins.
    covered: dict[str, tuple[bool, str, str]] = {}

    def rollup(line: StoryLine, ok: bool, why: str) -> None:
        for req in line.covers:
            prev = covered.get(req)
            if prev is None or (ok and not prev[0]):
                covered[req] = (ok, why, line.id)

    targets: list[tuple[str, StoryLine, bool]] = []
    own = led.stories.get(sid)
    if own and own.acceptance:
        targets.append((sid, own, True))
    if readable:
        blob = "\n".join(ids).replace("_", "-")
        for other, line in led.stories.items():
            if other != sid and line.acceptance and (
                    f"AC-{other}-" in blob or _linked(led, other, ids)):
                targets.append((other, line, False))

    for story_id, line, owner in targets:
        if not readable:
            if not owner:
                continue
            # The cause varies (no reporter, suite unrunnable, runner note) but the
            # consequence is one: no test name to attach to this behaviour. Keep
            # `WHY_UNREADABLE` as the prefix so `gap_kind` classifies the whole
            # branch as UNTRACED while the sentence still names the actual cause.
            detail = str(det.get("unrunnable") or det.get("test_note") or "")
            why = f"{WHY_UNREADABLE}: {detail}" if detail else WHY_UNREADABLE
            for i in range(1, line.acceptance + 1):
                note(story_id, i, False, {"why": why})
            # **Không** `rollup` ở đây (D-001, cùng lớp với dòng 155 ở nhánh mà bản
            # sửa ấy không phủ). `rollup` ghi mọi requirement story này `covers` là
            # không-xanh, mà chúng do các story **trước** sở hữu và đã VERIFIED —
            # nên một lượt không đọc được tên phép thử lật chúng sang REOPENED
            # trong khi không một phép thử đỏ nào được đọc ở đâu. Đo trên corpus
            # `todo`: FR-1, FR-2, FR-4 và FR-9 cùng lật do một lượt của
            # STORY-02-02 mà `test` tool_run có `ok=True`.
            #
            # Tiêu chí của **chính** story này vẫn ghi là chưa chứng minh (các
            # `note` ở trên, `gap_kind` xếp là UNTRACED): cái bỏ đi là việc lật
            # bản án của người khác, không phải việc thừa nhận story này chưa
            # chứng minh gì. Một requirement là hiện vật dùng chung giữa các
            # story, và nó không được đổi trạng thái vì "không đọc được kết quả".
            #
            # Không mở đường đạt-sai: một lượt không đọc được chỉ từng truyền
            # `False`, nên bỏ lời gọi này chỉ có thể ngăn một REOPENED sai, không
            # thể sinh ra một VERIFIED.
            continue

        cov = ac_coverage(story_id, line.acceptance, ids)
        linked = dict(_linked(led, story_id, ids))
        for i, t in linked.items():
            cov.setdefault(i, [])
            if t not in cov[i]:
                cov[i].insert(0, t)
        judged = []
        gap_whys = []                       # reason of each non-green criterion, in order
        for i, tests in cov.items():
            if not tests:
                if owner:
                    # A trace *was* declared (`aisef evidence <AC> --link`) but its
                    # test is not in this run: the absence is in the metadata, not
                    # in the product — say which id, so the fix is a one-liner.
                    lk = led.links.get(ac_code(story_id, i))
                    why = f"{WHY_TRACE_ABSENT}: {lk['test_id']}" if lk else WHY_NO_TEST
                    note(story_id, i, False, {"why": why})
                    judged.append(False)
                    gap_whys.append(why)
                continue
            red = [t for t in tests if t in failed]
            if not red and all(t in unexecuted for t in tests):
                # every test of this criterion was skipped or errored: observed, not verified
                note(story_id, i, False, {"test_id": tests[0], "tests": len(tests), "why": WHY_NOT_EXECUTED})
                judged.append(False)
                gap_whys.append(WHY_NOT_EXECUTED)
                continue
            # Source of a GAP must be a **red** test, not the first test in the
            # list: the reader of `aisef evidence` needs a name to open, not a
            # green name sitting next to the failure.
            src = {"test_id": (red or tests)[0], "tests": len(tests)}
            if i in linked:
                lk = led.links[ac_code(story_id, i)]
                src.update(via="traceability", by=str(lk.get("by") or ""),
                           why=str(lk.get("why") or ""))
            note(story_id, i, not red, src)
            judged.append(not red)
            if red:
                gap_whys.append("")         # a red test needs no sentence
        # Requirement is green when **its criteria** are green — not when the
        # whole run is green. A run red because of another story must not turn
        # this story's FR into a regression (measured on e9: FR-1/FR-11 were
        # falsely blamed on STORY-01-06 because the old rule read `e.ok`).
        story_green = all(judged) if judged else bool(e.ok)
        # The requirement is non-green *through* its criteria, so it inherits their
        # kind of absence (ADR-009 O2): when every non-green criterion gives the same
        # reason, that reason is the requirement's reason too, and `gap_kind` routes
        # both the same way. Mixed reasons fall back to the unspecific sentence, which
        # `gap_kind` reads as `unbuilt` — the expensive side, never the cheap one.
        # `landed` gates the whole rule: on an unlanded candidate the *green* criteria
        # are not proof either (measured on todo-cli, where dropping the gate reduced
        # nine requirement gaps of STORY-06-01 to "one criterion lacks a test" while
        # the other seven were green only in a worktree that never merged).
        why = "" if story_green else (
            gap_whys[0] if landed and gap_whys and len(set(gap_whys)) == 1 and gap_whys[0]
            else "story criteria not yet green")
        rollup(line, story_green, why)

    for req, (ok, why, owner) in covered.items():
        led.observe(req, _kind_of(req), ok=ok, at=at, story=sid, owner=owner,
                    attempt=attempt, candidate=cand, landed=landed,
                    source={"story": owner, **({"why": why} if why else {})})


def _linked(led: Ledger, story_id: str, ids: list[str]) -> list[tuple[int, str]]:
    """(criterion, test id) that a human declared as traceability for this
    story **and** present in this run. Declared but not run means nothing to say."""
    out = []
    for i in range(1, (led.stories[story_id].acceptance if story_id in led.stories else 0) + 1):
        lk = led.links.get(ac_code(story_id, i))
        if lk and str(lk.get("test_id")) in ids:
            out.append((i, str(lk["test_id"])))
    return out


def _kind_of(bid: str) -> str:
    up = bid.upper()
    if up.startswith("NFR"):
        return "nfr"
    if up.startswith("FR"):
        return "fr"
    if bid.startswith("qa:"):
        return "qa"
    if bid.startswith("mockup:"):
        return "mockup"
    return "ac"


def _epic_of(story_id: str) -> str:
    m = _EPIC_FROM_ID.match(story_id)
    return f"EPIC-{m.group(1)}" if m else "(no epic)"


def _attempt(e, sid: str, current: int) -> int:
    """Current attempt of the story — read from `agent_run` name (`STORY-x#2`)
    or `detail.attempt` of handoff/review. No guessing: if not found, keep current."""
    if e.kind == AGENT_RUN and e.name.startswith(sid):
        m = _ATTEMPT.search(e.name)
        if m:
            return int(m.group(1))
    raw = e.detail.get("attempt")
    if isinstance(raw, int) and raw > 0:
        return raw
    return current


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}
