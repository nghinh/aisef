"""Story size score — deterministic, each component explainable (ADR-004 R5).

`story.max_screen_states` (P2-12) measures **one** dimension: screen states.
Measurements from 2026-09-05 on e9 show that one dimension is insufficient —
STORY-01-01 has no screens yet took 61 developer turns on the first attempt
and 4 retries (14 declared paths, 9 after excluding manifest/lockfile; 7
acceptance criteria). This module sums five dimensions measurable **before
calling the model**, each with a named weight, and returns an explanation so
the reader can verify the number instead of trusting it.

Calibration (B4, retrospective 2026-09-05, zero agent cost — see ADR-004 §6 R5):
11 real stories with evidence (e9 STORY-01-01..01-06, `par` 5 stories),
comparing score against **first-attempt developer turns** (`turns` from the
first `agent_run` `<story>#1` in evidence):

| story | states | criteria | scope | fan-in | score | first turns |
|---|---|---|---|---|---|---|
| e9 01-01 | 0 | 7 | 9 | 1 | 12.5 | 61 |
| e9 01-02 | 0 | 7 | 10 | 2 | 14.0 | 42 |
| e9 01-03 | 0 | 4 | 3 | 1 | 6.5 | 57 |
| e9 01-04 | 9 | 7 | 13 | 1 | **23.5** | 89 / 90, 4 attempts, $79.67 |
| e9 01-05 | 5 | 7 | 10 | 1 | **18.0** | 91 — hit `max_turns` |
| e9 01-06 | 1 | 7 | 6 | 2 | 13.0 | 84 |
| par x5 | 0 | 2 | 2 | 0 | 3.0 | 24 / 41 / 37 / — / 8 |

Spearman(score, first_turns) = **0.88** on 10 stories with turn counts (par
STORY-02-01 reports `turns = 0` — client did not report, excluded from sample).
Default threshold 16 blocks exactly the two most expensive stories (01-04 and
01-05) and does not touch 01-01/01-02/01-06 (12.5-14.0), 01-03 (6.5) or
`par` (3.0). It does **not** catch two other `max_turns` hits (e9 01-01 at
61/60 turns, `par` 01-02 at 41/40) — both occurred under a lower `max_turns`
ceiling than the current one, so that is `run.max_turns`'s concern, not story
size's. See `docs/ADR-004-evidence-driven-epic-improvement.md` §6 R5.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULTS, Config
from .normalize import MANIFESTS, Story, is_lockfile

#: One screen state the story **builds for the first time**. Most expensive
#: dimension measured: 01-04 (9 states) 89 turns, 01-05 (4 + 1 revisit) 91.
SCREEN_STATE_WEIGHT = 1.0
#: One acceptance criterion. Same magnitude as one state: e9 every story has
#: 7 criteria, and the 4-criteria story (01-03) was markedly cheaper.
ACCEPTANCE_WEIGHT = 1.0
#: One path in write scope (excluding manifest/lockfile — they are automatic
#: side-effects, see `normalize.with_lockfiles`). Half weight: 01-01 has 9
#: paths yet finished in 2 turns.
WRITE_SCOPE_WEIGHT = 0.5
#: One story that depends on this story. High fan-in means errors here
#: propagate widely, so the session must be more careful.
FAN_IN_WEIGHT = 1.0
#: A **neighboring story** with VERIFIED behaviors whose write scope overlaps
#: this story's (ledger, R2). Counted by owning story, not by behavior: on
#: e9 2026-09-06, STORY-01-07 touches 31 behaviors of 3 stories (01-04/05/06)
#: — counting behaviors would add +15.5 points, blocking a 12.5 story at 28.0.
#:
#: Weight is **0 until calibrated**: the B4 table (Spearman 0.88) was built
#: on stories that ran when the ledger was empty, so this dimension contributed
#: zero points to that correlation. Trying 0.5 on the real e9 ledger (2026-09-06)
#: blocks three near-threshold stories (02-03 15.0->17.0; 03-03 15.5->17.0;
#: 05-01 16.0->17.5) with a weight that has no turn-count evidence behind it.
#: The component is still counted and recorded in `complexity.json` for future
#: calibration when enough stories have both a ledger and turn counts (see
#: `divergence`); at that point, set the weight from measured data.
VERIFIED_TOUCHED_WEIGHT = 0.0

#: Auto-written calibration filename, in `_bmad-output/`.
CALIBRATION_FILE = "complexity.json"

#: "Done in one short run" = first attempt uses below this fraction of `run.max_turns`.
SHORT_TURN_FRACTION = 0.5

#: How many stories must diverge in the same direction before concluding the
#: threshold is wrong. One divergent story is normal; two is a signal.
DIVERGENCE_MIN = 2

#: Markers indicating a screen state is **secondary** — can be split to a
#: follow-up story. Primary state is the screen in the normal/happy path;
#: the rest are edge cases. Used for split suggestions, not for scoring.
SECONDARY_STATE_MARKERS = (
    "rỗng", "trống", "empty", "lỗi", "error", "thất bại", "fail",
    "offline", "ngoại tuyến", "đang tải", "loading", "chưa sẵn sàng",
    "focus", "không khớp", "không tồn tại", "sắp cạn", "quá hạn", "trùng",
)

_DEV_RUN = re.compile(r"^(?P<story>[\w.-]+)#(?P<n>\d+)$")

#: Stories in a wave run in parallel threads, and `record` is a read-modify-write
#: of the whole file: without a lock, two stories finishing simultaneously lose a row.
_WRITE_LOCK = threading.Lock()


@dataclass(frozen=True)
class Component:
    """One dimension of the score, with evidence of how it was counted."""

    name: str
    count: int
    weight: float
    evidence: str = ""

    @property
    def points(self) -> float:
        return round(self.count * self.weight, 2)

    def line(self) -> str:
        out = f"{self.name} {self.count}×{self.weight:g} = {self.points:g}"
        return f"{out} ({self.evidence})" if self.evidence else out


@dataclass(frozen=True)
class Score:
    story_id: str
    components: tuple[Component, ...] = field(default_factory=tuple)

    @property
    def total(self) -> float:
        return round(sum(c.points for c in self.components), 2)

    def get(self, name: str) -> Component:
        for c in self.components:
            if c.name == name:
                return c
        return Component(name, 0, 0.0)

    def as_dict(self) -> dict:
        return {
            "story_id": self.story_id,
            "total": self.total,
            "components": {c.name: {"count": c.count, "weight": c.weight,
                                    "points": c.points, "evidence": c.evidence}
                           for c in self.components},
        }

    def explain(self) -> str:
        return f"{self.total:g} = " + " + ".join(
            c.line() for c in self.components if c.count
        )


# ------------------------------------------------------------ components


def screen_states(
    story: Story,
    *,
    experience=None,
    owned: dict[str, str] | None = None,
) -> list[tuple[str, int]]:
    """States the story must build, per screen.

    A screen already built by a **different** story counts as 1 (revisit),
    not all its states — preserving the `preflight.screen_owners` rule
    calibrated on e9 01-05.
    """
    out: list[tuple[str, int]] = []
    for sid in story.screens:
        scr = experience.by_id(sid) if experience is not None else None
        cua_minh = owned is None or owned.get(sid, story.id) == story.id
        out.append((sid, max(1, len(scr.states)) if (scr is not None and cua_minh) else 1))
    return out


def scope_paths(story: Story) -> list[str]:
    """Write-scope paths **as declared by the story** — excluding manifests
    and lockfiles, since the harness adds those automatically
    (`normalize.with_lockfiles`)."""
    return [
        p for p in story.write_scope
        if not is_lockfile(p) and p.strip("/").rsplit("/", 1)[-1] not in MANIFESTS
    ]


def fan_in_counts(stories) -> dict[str, int]:
    """story -> number of stories that depend on it."""
    out: dict[str, int] = {}
    for s in stories:
        for dep in getattr(s, "depends_on", []) or []:
            out[dep] = out.get(dep, 0) + 1
    return out


def _within(path: str, scope: str) -> bool:
    p, s = path.strip("/").split("/"), scope.strip("/").split("/")
    return len(p) >= len(s) and p[: len(s)] == s


def verified_touched(story: Story, ledger: dict | None,
                     scopes: dict[str, list[str]] | None = None) -> list[str]:
    """VERIFIED behaviors of **other stories** whose write scope overlaps this story's.

    The behavior ledger (R2, `control/ledger.py`) records the story that *owns*
    a behavior, not files — files come from that story's write scope, looked up
    via ``scopes`` (id -> write_scope, read from `stories.index.json`). Records
    that already have `files` / `write_scope` are also used. Missing ledger,
    missing index, or behaviors with no file mapping result in this dimension
    = 0 — missing data must not become fabricated points. Behaviors owned by
    this story (re-runs) are excluded: those are its goal, not something it must
    preserve. REOPENED behaviors where `regressed_by` is this story itself **are**
    counted — it just broke them, so it must fix them.
    """
    if not isinstance(ledger, dict):
        return []
    scope = scope_paths(story)
    if not scope:
        return []
    scopes = scopes or {}
    out: list[str] = []
    for bid, rec in (ledger.get("behaviors") or {}).items():
        if not isinstance(rec, dict):
            continue
        status = str(rec.get("status", "")).lower()
        # REOPENED **by this story** is still something it must preserve: excluding
        # them from the list means attempt 2 gets a "preserve" gate pass while the
        # previous story's tests are still red — measured on par B3 2026-09-06:
        # attempt 2 only had AC-01-01-2, lost AC-01-01-1 and FR-1 that attempt 1
        # just broke. REOPENED by another story is excluded: this story did not
        # break it, marking it as failed would be unfair.
        if status != "verified" and not (
            status == "reopened"
            and str(rec.get("regressed_by") or "").startswith(story.id + "#")
        ):
            continue
        owner = str(rec.get("story") or "")
        if owner == story.id:
            continue
        files = rec.get("files") or rec.get("write_scope") or scopes.get(owner) or []
        if isinstance(files, str):
            files = [files]
        if any(_within(str(f), s) or _within(s, str(f)) for f in files for s in scope):
            out.append(str(bid))
    return sorted(out)


def read_scopes(project: Path | str | None) -> dict[str, list[str]]:
    """id -> write_scope from `_bmad-output/stories.index.json`; empty if missing."""
    if project is None:
        return {}
    path = Path(project) / "_bmad-output" / "stories.index.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = data.get("stories", []) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = list(items.values())
    return {str(s.get("id")): list(s.get("write_scope") or [])
            for s in items if isinstance(s, dict) and s.get("id")}


def read_experience(project: Path | str | None):
    """`_bmad-output/EXPERIENCE.md` if readable, otherwise `None`."""
    if project is None:
        return None
    from .experience import parse_experience_file

    path = Path(project) / "_bmad-output" / "EXPERIENCE.md"
    if not path.is_file():
        return None
    try:
        return parse_experience_file(path)
    except (OSError, ValueError):
        return None


def read_ledger(project: Path | str | None) -> dict | None:
    """`_bmad-output/ledger.json` if it exists. Returns `None` if missing, no error."""
    if project is None:
        return None
    path = Path(project) / "_bmad-output" / "ledger.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def score_story(
    story: Story,
    *,
    project: Path | str | None = None,
    experience=None,
    owned: dict[str, str] | None = None,
    fan_in: int = 0,
    ledger: dict | None = None,
) -> Score:
    """Size score for a story. Pure function on available data, no model calls."""
    if experience is None:
        experience = read_experience(project)
    per_screen = screen_states(story, experience=experience, owned=owned)
    states = sum(n for _, n in per_screen)
    scope = scope_paths(story)
    if ledger is None:
        ledger = read_ledger(project)
    touched = verified_touched(story, ledger, read_scopes(project))
    behaviors = (ledger or {}).get("behaviors") or {}
    # Behaviors without an owning story (legacy records, manual) count individually.
    owners = {str(behaviors.get(b, {}).get("story") or b) for b in touched}

    return Score(story.id, (
        Component("screen_states", states, SCREEN_STATE_WEIGHT,
                  ", ".join(f"`{sid}` {n}" for sid, n in per_screen)),
        Component("acceptance", len(story.acceptance_criteria), ACCEPTANCE_WEIGHT),
        Component("write_scope", len(scope), WRITE_SCOPE_WEIGHT,
                  ", ".join(f"`{p}`" for p in scope[:4]) + ("…" if len(scope) > 4 else "")),
        Component("fan_in", int(fan_in), FAN_IN_WEIGHT),
        Component("verified_touched", len(owners), VERIFIED_TOUCHED_WEIGHT,
                  f"{len(touched)} behaviours: " + ", ".join(touched[:4])
                  + ("…" if len(touched) > 4 else "") if touched else ""),
    ))


# ------------------------------------------------------------ split suggestions


def split_suggestion(
    story: Story,
    score: Score,
    *,
    experience=None,
    owned: dict[str, str] | None = None,
) -> str:
    """How to split this story, **deterministic**, based on the heaviest dimension.

    Three strategies in priority order: multiple screens -> one story per
    screen; one screen with many states -> primary states first, edge-case
    states next; no screens -> split by acceptance criteria groups. None of
    these require a model: the planner can act on them immediately.
    """
    per = screen_states(story, experience=experience, owned=owned)
    minh_dung = [(sid, n) for sid, n in per
                 if owned is None or owned.get(sid, story.id) == story.id]

    if len(minh_dung) > 1:
        return ("split by screen — one story per screen: "
                + "; ".join(f"`{sid}` ({n} states)" for sid, n in minh_dung))

    if minh_dung and minh_dung[0][1] > 1 and experience is not None:
        sid = minh_dung[0][0]
        scr = experience.by_id(sid)
        states = list(scr.states) if scr is not None else []
        chinh = [s for s in states if not _is_secondary(s)]
        phu = [s for s in states if _is_secondary(s)]
        if chinh and phu:
            return (f"split `{sid}` by state group — first story builds primary states "
                    f"({', '.join(chinh)}); next story builds secondary states "
                    f"({', '.join(phu)})")

    ac = story.acceptance_criteria
    if len(ac) > 1:
        nua = math.ceil(len(ac) / 2)
        return (f"split by acceptance criteria group — first story keeps AC 1–{nua}, next story "
                f"keeps AC {nua + 1}–{len(ac)}; divide `write_scope` to match the two groups "
                f"({score.get('write_scope').count} paths)")

    return "split story: reduce write scope or move acceptance criteria to a follow-up story"


def _is_secondary(state: str) -> bool:
    low = state.lower()
    return any(m in low for m in SECONDARY_STATE_MARKERS)


# ------------------------------------------------------------ calibration


def observed(artifact_root: Path | str, story_id: str, *, max_turns: int = 0) -> dict:
    """**Actual** numbers for a story, read from evidence: first-attempt
    developer turns, number of attempts, whether `max_turns` was hit.

    First attempt is the first `agent_run` named `<story>#1` in the evidence
    store: that session has no prior feedback, so it measures exactly "how hard
    is this story on first read." Re-running the story after plan edits does
    not overwrite that number.
    """
    from ..harness.observe import AGENT_RUN, EvidenceStore

    ev = EvidenceStore(artifact_root).read(story_id)
    first, attempts, hit = None, 0, False
    for e in ev.of(AGENT_RUN):
        m = _DEV_RUN.match(e.name or "")
        if not m or m.group("story") != story_id:
            continue  # review/security runs are not developer attempts
        turns = int(e.detail.get("turns") or 0)
        attempts = max(attempts, int(m.group("n")))
        if first is None:
            first = turns
        if str(e.detail.get("error") or "") == "max_turns" or (
            max_turns and turns >= max_turns
        ):
            hit = True
    return {"first_turns": first, "attempts": attempts, "max_turns_hit": hit,
            "max_turns": int(max_turns)}


def calibration_path(artifact_root: Path | str) -> Path:
    return Path(artifact_root) / CALIBRATION_FILE


def load_calibration(artifact_root: Path | str) -> dict:
    path = calibration_path(artifact_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = data.get("stories") if isinstance(data, dict) else None
    return rows if isinstance(rows, dict) else {}


def record(
    artifact_root: Path | str,
    story: Story,
    *,
    score: Score,
    config: Config | None = None,
) -> dict:
    """Record a calibration row for a completed story: predicted score, each
    component, and actual numbers measured from evidence.

    This table is the only thing that tells whether the threshold is still
    correct. Without it, every doubt requires manually digging through
    evidence — and thresholds get adjusted by gut feeling."""
    cfg = config or Config(dict(DEFAULTS))
    row = score.as_dict() | observed(
        artifact_root, story.id, max_turns=int(cfg["run.max_turns"])
    ) | {
        "threshold": float(cfg["story.max_complexity"]),
        "at": round(time.time(), 3),
    }
    path = calibration_path(artifact_root)
    with _WRITE_LOCK:
        rows = load_calibration(artifact_root)
        rows[story.id] = row
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "stories": rows}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    return row


def divergence(rows: dict) -> list[str]:
    """Is the threshold diverging from data — reads the calibration table, no guessing.

    Two divergence directions, each requiring ``DIVERGENCE_MIN`` stories:
    threshold **too high** (stories below threshold still hit `max_turns`)
    and threshold **too low** (stories above threshold finish quickly on the
    first attempt).
    """
    qua_cao, qua_thap = [], []
    for sid, r in sorted(rows.items()):
        if not isinstance(r, dict):
            continue
        total, limit = float(r.get("total") or 0), float(r.get("threshold") or 0)
        turns, cap = r.get("first_turns"), int(r.get("max_turns") or 0)
        if total <= limit and r.get("max_turns_hit"):
            qua_cao.append(f"{sid} ({total:g} ≤ {limit:g}, hit max_turns)")
        elif (total > limit and int(r.get("attempts") or 0) <= 1 and turns
                and cap and turns <= cap * SHORT_TURN_FRACTION):
            qua_thap.append(f"{sid} ({total:g} > {limit:g}, done in first run {turns} turns)")

    out = []
    if len(qua_cao) >= DIVERGENCE_MIN:
        out.append(f"`story.max_complexity` appears **too high**: {', '.join(qua_cao)}")
    if len(qua_thap) >= DIVERGENCE_MIN:
        out.append(f"`story.max_complexity` appears **too low**: {', '.join(qua_thap)}")
    return out


def spearman(xs, ys) -> float:
    """Spearman rank correlation, with tied-rank handling. NaN if not computable.

    Used to validate the calibration table (B4): does the predicted score rank
    stories in the same order as actual turn cost.
    """
    n = len(xs)
    if n < 2 or n != len(ys):
        return float("nan")
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def _ranks(values) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        share = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = share
        i = j + 1
    return out


__all__ = [
    "ACCEPTANCE_WEIGHT",
    "CALIBRATION_FILE",
    "Component",
    "FAN_IN_WEIGHT",
    "SCREEN_STATE_WEIGHT",
    "Score",
    "VERIFIED_TOUCHED_WEIGHT",
    "WRITE_SCOPE_WEIGHT",
    "divergence",
    "fan_in_counts",
    "load_calibration",
    "observed",
    "read_experience",
    "read_ledger",
    "record",
    "score_story",
    "scope_paths",
    "screen_states",
    "spearman",
    "split_suggestion",
]
